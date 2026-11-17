# Задания индексации, повтор и очистка snapshots

Change `ingest-jobs-recovery` плана [2.0](development-plan-v2.md). Каждый запуск
`index-sources` записывает задание в `ingest_jobs` (миграция 0016) и печатает его ID.

## Состояние задания

| Поле | Значение |
| --- | --- |
| state | RUNNING → SUCCEEDED или FAILED |
| stage | INDEX (capture, анализ, загрузка BUILDING), PUBLISH (validation и публикация при `--publish`) |
| attempt | номер попытки, с 1 |
| snapshot_id | snapshot попытки после успешного INDEX; NULL, если его удалила очистка |
| parameters | аргументы запуска (root, repository_key, profile, dialect, naming policy, connections, publish) |
| failure | последняя ошибка: type, message; для AdapterError — adapter_key, stage и issues с path и diagnostic |

Запись создаётся после регистрации репозитория: ошибки аргументов до этого
(нет каталога, нечитаемый файл connections) задания не создают.

Работающее задание держит сессионную advisory-блокировку PostgreSQL. Процесс,
завершившийся без отчёта (kill, обрыв соединения), теряет её автоматически — так
брошенное RUNNING отличается от живого без таймаутов.

## Команды

```bash
uv run code-crawler jobs list                 # 50 последних заданий, JSON
uv run code-crawler jobs retry JOB_UUID       # следующая попытка с теми же параметрами
uv run code-crawler snapshot gc --building-older-than 24 --keep-retired 3
```

`jobs retry` принимает FAILED и брошенное RUNNING задание; attempt увеличивается,
failure очищается. Задание, которое выполняет другой процесс, и SUCCEEDED
отклоняются. Повтор безопасен: попытка строит новый BUILDING snapshot, а публикация
идёт через CAS по её собственному base pointer, поэтому чужая публикация не
перезаписывается. Snapshot упавшей попытки остаётся BUILDING до очистки.

`snapshot gc` требует хотя бы один параметр и свободное соединение; API отклоняет
отрицательный/нечисловой возраст, дробный retention и отсутствие опций до любых
изменений. Reap заданий и удаление выполняются одной транзакцией:

- preflight требует полностью применённые известные миграции и проверяет реестр,
  `uuid snapshot_id` и порядок immediate/cascading FK; общий advisory-lock миграций
  исключает одновременную штатную миграцию;
- посторонние snapshot-bearing таблицы попадают в `ignored_tables`, но не в DELETE.
  Неизвестный inbound FK к UCM (включая ON DELETE CASCADE) запрещает GC до удаления;
- GC блокирует repository перед snapshot, повторно проверяет state, publication
  pointer и RUNNING job. Занятые строки и snapshots с reader lease пропускаются;

- сначала брошенные RUNNING задания помечаются FAILED;
- `--building-older-than ЧАСЫ` удаляет BUILDING snapshots старше порога, если у их
  репозитория нет работающего задания;
- `--keep-retired N` оставляет N последних (по created_at) RETIRED snapshots на
  репозиторий и удаляет остальные вместе с фактами, manifests и validation receipt.

PUBLISHED, READY и VALIDATING не удаляются никогда; VALIDATING после неудачной
validation остаётся для диагностики. Удалённый RETIRED нельзя вернуть rollback'ом.
Расписания нет: retention запускается только явной командой. Записи заданий
переживают удаление snapshot.

GC удаляет строки только из явного реестра `_SNAPSHOT_TABLES` в `jobs.py`:
факты UCM, snapshot manifests, source links, validation receipts и C01 search
generations/documents/publications. Search generations удаляются перед фактами:
каскад удаляет sealed documents вместе с generation. Наличие колонки
`snapshot_id` или префикса `ucm_` не включает постороннюю таблицу в очистку.
`ingest_jobs` сохраняется через `ON DELETE SET NULL`; canonical publication pointers и общие
source blobs не входят в реестр. При добавлении snapshot-таблицы миграцией нужно
явно дополнить реестр; integration test сверяет его с чистой схемой миграций.
Штатный GC отклоняет неполную схему. Только изолированный benchmark на историческом
префиксе миграций очищает собственный trial UUID по существующим таблицам реестра.
Счётчики учитывают строки до удаления, включая каскадно удалённые search documents.

Результат сохраняет `reaped_jobs`, `building`, `retired` и добавляет `deleted_rows`
(таблица → число удалённых строк, включая `ucm_snapshots`), `skipped`,
`skipped_repositories`, `ignored_tables`, `errors`. При SQL/FK/preflight ошибке API
выбрасывает `jobs.GCError` с `.report`, CLI печатает этот отчёт и завершает работу
с ненулевым кодом. После rollback списки удалённых snapshots и счётчики пусты;
диагностика содержит stage, тип, SQLSTATE/constraint, но не SQL DETAIL или source
bytes. Отмена также откатывает транзакцию и освобождает transaction locks.

`reader.published_reader` и поиск внутри транзакции (в том числе MCP) держат shared
transaction advisory lease выбранного snapshot. GC берёт exclusive lease только
через try-lock и пропускает используемую версию. Lease освобождается при commit,
rollback, отмене или разрыве соединения. SQL-читатели вне этих API должны явно
вызвать `snapshots.pin_snapshot` внутри своей транзакции. Обычный MVCC snapshot
не считается явным lease; новая постоянная таблица pins не вводится.

## Защита фактов

Факты и receipts по-прежнему immutable вне BUILDING. Миграция 0016 разрешает
DELETE для RETIRED только в транзакции с `SET LOCAL code_crawler.gc = 'on'`; её
ставит `jobs.collect_garbage`. Для PUBLISHED, READY и VALIDATING флаг не действует.

Этапы внутри INDEX (capture, analyze, load) в задании не различаются —
их показывает прогресс CLI.

Saved resolver contexts and registered deployment mappings retain their selected
retired snapshots until explicitly released. GC excludes these retention owners
from deletion and serializes pin changes using a transaction advisory lock.
See [resolver-contexts.md](resolver-contexts.md).

Resolver-cache dependencies and entries are explicitly registered before their
canonical parents in the safe GC allowlist. Deleting any selected snapshot or
catalog generation invalidates dependent cache entries; these derivatives never
retain a snapshot. Active C04 cache hits use the same transaction snapshot leases
as uncached reads. See [resolver-cache.md](resolver-cache.md).

## Время GC

Замер `ucm-query-index-optimization` 2026-11-15: PostgreSQL 15.20, macOS arm64
(Apple M4), shared_buffers=128MB, сервер без другой нагрузки. Удаляется BUILDING
snapshot из 141 424 сущностей — копия опубликованного, загруженная `ingest_batch`.

| | Время, с |
| --- | ---: |
| загрузка snapshot (`ingest_batch`), 3 запуска | 25,7; 25,0; 24,8 |
| `collect_garbage` этого snapshot, 3 запуска | 120,9; 122,9; 124,0 |

GC впятеро дольше загрузки. Основное время уходит в COMMIT, где срабатывают
отложенные проверки внешних ключей: на каждую удалённую строку
родительской таблицы PostgreSQL ищет ссылающиеся строки во всех дочерних таблицах.
У части внешних ключей ссылающаяся колонка не входит ни в один индекс, и поиск
идёт по префиксу `snapshot_id` первичного ключа — по всем строкам snapshot в этой
таблице. Так устроены, например, `ucm_occurrences.target_symbol_id` и `scope_id`,
`ucm_type_refs.target_symbol_id`, `ucm_evidence.source_file_id`,
`ucm_scopes.parent_scope_id` и `owner_symbol_id`, `ucm_operations.scope_id`. Эта
часть растёт как произведение числа родительских и дочерних строк, то есть
квадратично от размера snapshot.

Проверка причины: с временными индексами `(snapshot_id, <колонка>)` на 19 таких
колонках GC того же snapshot занял 65,2 и 60,9 с вместо 122, а загрузка — 25,3 и
25,6 с. Индексы в схему не добавлены: это решение change
`b06-large-snapshot-gc-performance` (индексы против удаления порциями).

На snapshot больше 1 млн сущностей GC не замерялся: при квадратичном росте
удаление одной копии оценивается часами. До b06 большие snapshots стоит удалять
редко и вне окна индексации; GC по-прежнему атомарен и не трогает PUBLISHED.

E01 stores redacted per-job/attempt stage aggregates after the canonical transaction.
GC records a global admin-only observation, without attributing its total duration
to unrelated repositories. See [observability.md](observability.md).
