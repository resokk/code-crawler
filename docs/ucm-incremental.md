# Инкрементальная индексация UCM

`index_incremental(conn, repository_id, root, analyze, *, languages, analysis_version)`
строит новый BUILDING snapshot, используя текущий опубликованный как baseline.
Стандартный CLI `index` использует этот pipeline через registry и публикует
результат; `index --backend legacy` сохраняет прежний writer. UCM adapters
получают tuple SourceInput(file: SourceFile, content: bytes) и возвращают tuple
FileAnalysis(path, entities, dependencies). Анализатор вызывается один раз только
для выбранных файлов; пустой набор не вызывает callback. SourceFile создаёт
orchestrator; analyzer возвращает остальные сущности и явные file dependencies.
Каждая сущность имеет ровно один файл-владелец. Shared/global entities должны
получать единственного владельца, а не дублироваться во всех файлах.

Inventory включает все tracked regular files Git, включая metadata/config;
untracked, symlinks (в том числе через symlink directory), submodules и отсутствующие
файлы не читаются. languages задаёт mapping suffix→language с longest case-sensitive match (например,
{'.java': 'java', '.d.ts': 'typescript'}); файлы без adapter получают SourceFile language='unknown', но
не передаются analyze. Git conflicts отклоняются. Root обязан быть корнем Git.
Пути и dependencies — canonical relative POSIX paths без traversal.

Git diff --name-only -z --no-renames между baseline commit и текущим HEAD даёт
список Git changes в плане. Авторитетны SHA-256 фактических bytes и language:
они выявляют также staged/unstaged изменения при неизменном HEAD. Если baseline
commit больше недоступен, достаточно fingerprint inventory. Rename трактуется
как delete+add. Source fingerprint snapshot вычисляется из canonical JSON списка
[path,content_sha256,language], отсортированного по path.

Изменения/добавления/удаления запускают транзитивную invalidation по прежним
зависимостям dependent→dependency. Зависимости включают явные adapter dependencies
и структурные ссылки между сущностями разных файлов (включая Evidence).
Отсутствующая dependency допустима как negative dependency: появление tracked
файла позже инвалидирует dependent. Внешние репозитории не участвуют.

Переиспользование допускается только с полным persisted file ownership/dependency
manifest и тем же analysis_version/languages. Изменение профиля или baseline без
manifest вызывает полный переразбор поддерживаемых файлов. Версия должна учитывать
изменения parser/resolver/config semantics. Незаявленные динамические зависимости
не угадываются: полнота explicit dependency extraction — обязанность adapter.

Исходники читаются один раз: captured inventory (`_Worktree`: commit, branch,
dirty, Git listing, SourceInput, stat каждого файла) создаётся в `_capture` и
передаётся дальше — `index_sources` и `index_java_*` отдают его в
`index_incremental(captured=...)`, без повторного чтения для prepare и анализа.
Перед записью `_verify` заново сверяет HEAD, branch, dirty и Git listing, а файлы
сравнивает по stat (inode, size, mtime, ctime); перечитываются и сверяются по
SHA-256 только файлы с изменившимся stat. Если исходники изменились во время
анализа, операция отклоняется. Анализатор должен использовать переданные
immutable bytes. При file read также проверяется стабильность stat. Это не
filesystem snapshot: транзитные изменения, вернувшиеся к тем же bytes, и
перезапись на месте с прежними inode/size/mtime/ctime не обнаруживаются.

Старые facts изменённых/удалённых файлов исключаются, остальные берутся из
immutable baseline; SourceFile заново формируются из текущих bytes. Итоговый UcmBatch
проходит полную validation. Отсутствующая/неверная ссылка не заменяется старым
фактом. Ошибка parser, Git или validation не переключает публикацию.

Миграция 0006 добавляет ingest_snapshot_profiles, ingest_file_entities и
ingest_file_dependencies. Их записи immutable с VALIDATING, как canonical facts.
Canonical COPY и manifests фиксируются одной транзакцией. Пустой BUILDING
snapshot metadata может остаться после DB failure; частичных facts/manifests нет.
Результат содержит snapshot_id, base_snapshot_id и IncrementalPlan. Публикация
отдельная через API: validate_snapshot, затем publish_snapshot(expected_snapshot_id=base).
CLI `index-sources --publish` выполняет эту последовательность автоматически;
ручные команды: [canonical-publication-cli.md](canonical-publication-cli.md).
Если baseline pointer успел измениться, CAS не позволит затереть новую публикацию.

Переиспользуется разбор, но итоговый полный batch всё ещё читается/хранится в
памяти одним экземпляром; в новый snapshot он загружается COPY порциями в одной
транзакции (см. [ucm-ingestion.md](ucm-ingestion.md)). Server-side row cloning,
streaming, CLI switch и language-specific extraction/resolution — следующие
changes. Для полной локальной resolution adapter может использовать собственный
контекст; callback обязан вернуть факты каждого запрошенного файла ровно один раз.

Общий SourceAdapter registry описан в [source-adapters.md](source-adapters.md).
Prepared registry version объединяет descriptors и фактические catalog versions.

Инвалидация по адаптерам: `index_incremental(scopes=...)` получает по одному
`AnalysisScope(key, analysis_version, fingerprint, suffixes)` на адаптер;
fingerprint — SHA-256 от descriptor manifest и версии prepared catalog. Миграция
0015 хранит их в `ingest_snapshot_adapters` (строка на адаптер в snapshot). Если
общий profile изменился, а у baseline есть эти строки, полного переразбора нет:
инвалидируются только файлы адаптеров с другим (или отсутствующим) fingerprint,
и далее — транзитивно их dependents по обычным file dependencies, в том числе в
других языках. Так изменение Java catalog не трогает Groovy и PL/Plus, пока их
факты не ссылаются на переразбираемые Java-файлы. Baseline без строк адаптеров
(создан до 0015 или без scopes) переразбирается целиком. Snapshot остаётся один
на все адаптеры.
SOURCE_ANALYSIS reports являются обычными file-owned facts: no-change reuse
сохраняет diagnostics/capabilities без повторного callback и без process cache.

## Reproducible bytes

Migration 0017 сохраняет captured source bytes (clean и dirty) как immutable,
repository-scoped content-addressed blobs. Snapshot/file links с origin
CAPTURED_WORKTREE записываются атомарно с facts/manifests. Новые snapshots без
полного архива не становятся READY/PUBLISHED. No-change indexing переиспользует
blob hashes, а Evidence восстанавливается без checkout. Контракт и API:
[source-evidence.md](source-evidence.md).

## Порционная индексация

`index_incremental` больше не собирает полный batch в памяти:

- baseline читается запросами (файлы, manifests, зависимости), а не загружается
  целиком;
- выбранные файлы анализируются срезами по 64: `analyze` вызывается по разу на
  срез, а не один раз на все файлы; каждый срез проверяется и записывается в приватный безымянный disk spool
  вне write transaction; staging получает готовые порции после анализа;
- факты переиспользуемых файлов копируются из baseline внутри БД (`INSERT ...
  SELECT` по manifest), вместе с их ownership и зависимостями;
- структурные зависимости между файлами вычисляются в БД: ссылки каждого файла
  соединяются с manifest владельцев.

B03 отделяет анализ и нормализацию от write transaction. Данные одной порции
нормализуются в COPY rows и сохраняются в приватный `TemporaryFile` (0600,
без имени на Linux); rows не накапливаются в RAM на весь snapshot. Spool содержит
чувствительные canonical facts, не поисковую redacted-проекцию. Он не принимает
внешние пути/данные и используется только текущим процессом. Завершение, ошибка,
отмена и падение процесса закрывают descriptor; постоянного spool/resume нет.

Baseline удерживается shared session advisory lease, без MVCC-транзакции или
repository row lock. Он может стать RETIRED при конкурентной публикации, но GC
не удалит его до завершения clone. Возвращаемый base_snapshot_id остаётся тем же;
обычная публикация по CAS отклонит устаревший результат.

Исходники проверяются перед записью и повторно после archive/manifests/FK checks
перед commit. Создание BUILDING snapshot, staging, cloning и архив остаются одной
атомарной транзакцией: ошибка/отмена не оставляют частично записанных facts.
CPU-анализ в ней не выполняется. COPY/clone, архивные checksum, проверка worktree
и FK/commit могут оставаться дорогими; B03 не обещает фиксированный timeout для
записи или строгий общий RSS. Captured bytes и catalogs по-прежнему в памяти;
порция ограничена 64 файлами, не числом facts/байтов (это B05).

IncrementalResult дополнительно сообщает preparation_seconds (нормализация,
анализ и spool после planning), write_transaction_seconds (включая commit),
spool_bytes. Capture/catalog preparation и чтение baseline в эти времена не входят.
После crash существующий jobs retry начинает заново; server rollback и закрытие
session снимают leases/temp tables, именованных spool-сирот не остаётся.

Что изменилось в проверках. До записи по-прежнему проверяются: каждая сущность и
каждый FileAnalysis строгим JSON, repository_id, «каждый запрошенный файл ровно
один раз»; ссылки и типы проверяют FK, дубликаты ID и двойное владение — первичные
ключи (ошибка PostgreSQL, а не ValueError). Межсущностные семантические правила
`UcmBatch` при индексации больше не выполняются: их проверяет `validate_snapshot`
до READY. BUILDING snapshot с такими нарушениями может быть создан, но не может
быть опубликован.

Замер на 400 Java-файлах (124 тыс. сущностей), пик памяти процесса при индексации:
653 МБ до изменений, 278 МБ первый запуск, 190 МБ повторный с переиспользованием
306 файлов из 400. Оставшийся рост даёт каталог Java (символы и синтаксические
деревья всех файлов).

### B03 reproducible transaction measurement

Opt-in benchmark creates/drops only `crawler_transaction_<uuid>` databases and
uses the same generated Java/SQL fixture as query benchmarks (199 groups = 400
files). Requires PostgreSQL 15/CREATEDB; does not index an existing repository:

```sh
TEST_DATABASE_URL=postgresql://... uv run python -m code_crawler.transaction_benchmark \
  --groups 199 --output /tmp/b03-candidate.json
```

Run in a fresh process for RSS comparison. The report includes code commit/file
hashes, harness and fixture digests, host/settings, sampled max backend transaction
age, calls observed inside a transaction, spool bytes and preparation/write phases.
`index_seconds` excludes capture/catalog preparation (reported separately),
validation/publication. Peak RSS is through indexing, including the catalog;
validation time is separate. Canonical digest removes snapshot UUIDs and compares
all subtype/auxiliary facts plus file manifests/dependencies. One paired local run
is evidence of transaction separation, not a statistical throughput/RAM SLA.

#### Recorded B03 comparison

[Raw PG15 report](benchmarks/b03-transactions-pg15.json): baseline `6eaa984`,
candidate `0844725`, 400 Java files / 140717 entities, identical fixture/harness and
normalized canonical digest; both snapshots validated. One sequential run each,
Linux / Python 3.12.14 / PostgreSQL 15.20, CPU/settings/limits in the report.

| Metric | Before | B03 |
| --- | ---: | ---: |
| Index seconds (excluding capture/catalog/validation) | 72.05 | 70.46 |
| Maximum sampled backend transaction age, seconds | 72.03 | 25.11 |
| Analyzer calls inside transaction / all calls | 7 / 7 | 0 / 7 |
| Peak client RSS through indexing, MiB | 405.74 | 428.97 |
| New preparation / write seconds | n/a | 45.31 / 25.11 |
| Spool bytes | n/a | 64191473 |

Transaction age dropped about 65%; total indexing time was similar. Peak RSS grew
about 5.7%, so this is **not** a memory reduction claim. Catalog/capture memory,
large single-file analyses and PostgreSQL buffers/trigger queues remain separate
B02/B05 concerns. One ordered local pair is not a latency SLA; cache/load bias and
sampling resolution remain limitations. No production sources/databases used.

To reproduce the baseline with exactly the same harness:

```sh
git worktree add --detach /tmp/crawler-b03-parent 6eaa984
cp src/code_crawler/transaction_benchmark.py /tmp/b03-measure.py
PYTHONPATH=/tmp/crawler-b03-parent/src TEST_DATABASE_URL=postgresql://... \
  uv run --locked python /tmp/b03-measure.py --groups 199 --output /tmp/b03-before.json
TEST_DATABASE_URL=postgresql://... uv run --locked python -m code_crawler.transaction_benchmark \
  --groups 199 --output /tmp/b03-after.json
git worktree remove /tmp/crawler-b03-parent
```

Opt-in Java process preparation preserves captured-byte/catalogue identity and
ordered slices. The registry supplies an optional `analysis_complete` callback to
release processes after preparation and before the write transaction; finally
cleanup covers errors/cancellation. PostgreSQL and row normalization remain in the
parent. See [parallel-snapshot-preparation.md](parallel-snapshot-preparation.md).
