# Поисковые документы

Change `search-document-projections` плана [2.0](development-plan-v2.md):
`code_crawler.search_documents.project(entities)` превращает факты UCM в текстовые
документы для полнотекстового и векторного поиска. Вход — сущности одного snapshot
(например, `UcmBatch.entities`), выход — итератор `SearchDocument`.

Чистая функция сохранена для совместимости. C01 добавляет отдельный API
`code_crawler.search_storage` и миграцию `0021_search_document_persistence.sql`.
Эмбеддинги и подключение к lexical/vector retrieval остаются отдельными changes.

## Документ

| Поле | Значение |
| --- | --- |
| `id` | `doc:` + SHA-256 от вида и ID сущности; стабилен между версиями |
| `kind` | SYMBOL, SQL_STATEMENT, DATABASE_OBJECT, CALL_SUMMARY, ORM_MAPPING, ORM_QUERY |
| `entity_id` | сущность UCM, из которой построен документ |
| `title`, `text` | заголовок и строки фактов |
| `language`, `path` | язык и путь файла сущности, если у неё есть место в исходниках |
| `content_sha256` | хеш заголовка и текста: меняется только вместе с содержимым |

Результат детерминирован: не зависит от порядка входных сущностей, строки внутри
документа отсортированы.

## Виды

- **SYMBOL** — класс, метод, конструктор, поле любого адаптера (Java, Groovy,
  PL/Plus): вид, полное имя с типами параметров, тип результата или поля, язык,
  файл и строки. Параметры и локальные переменные своих документов не получают.
- **SQL_STATEMENT** — операция, диалект, статус разбора и его причины, текст
  запроса, доступы к таблицам и колонкам (с ролью; несвязанные помечены
  `[UNBOUND]`/`[AMBIGUOUS]`), исполнители через EXECUTES_STATEMENT с certainty.
  Если такой связи нет — строка `no execution fact recorded`.
- **DATABASE_OBJECT** — вид и полное имя объекта, ключ и версия БД.
- **CALL_SUMMARY** — для символа с вызовами: разрешённые цели (`calls:`),
  вызывающие (`called by:`), число неразрешённых и неоднозначных вызовов с
  причиной, coverage анализа вызовов.

- **ORM_MAPPING** — вид, entity name, явно сохранённые имена объектов БД,
  status и причины неполноты.
- **ORM_QUERY** — вид запроса, name, текст (если сохранён в UCM), status и причины.

## Только факты

Документ пересказывает сохранённые сущности и связи и ничего не выводит сам:

- у каждой упомянутой связи указана certainty (`[INFERRED]`, `[STATIC_PROVEN]`);
- неразрешённые вызовы считаются, но цель не называется и не угадывается;
- нет обобщений вроде «сервис работы с пользователями» — только имена, типы, места
  и связи из UCM.

## Ограничения

- Проверено на Java и Groovy; PL/Plus проходит тем же общим путём (Symbol,
  SqlStatement), но отдельным тестом не покрыт. CFT-селекторы PL/Plus
  в документы не попадают.
- Текст на английском, формат строк — часть контракта: его изменение меняет
  `content_sha256` всех документов.

## Persistence: контракт C01

`rebuild_search_documents(conn, repository_id, snapshot_id, *,
allowed_repository_ids, policy_version, redact, expected_generation_id) -> UUID`
создаёт поколение только для READY/PUBLISHED/RETIRED snapshot. BUILDING и
VALIDATING отвергаются. Соединение должно быть без внешней транзакции.
`expected_generation_id=None` означает отсутствие прежнего поколения;
при повторной сборке нужен текущий ID. Конкурентная смена pointer вызывает
`ValueError` и rollback всей новой сборки. Канонические факты, state и UCM
publication pointer не изменяются.

Таблицы:

- `search_index_generations`: UUID поколения, repository/snapshot,
  `projection_version=search-documents-v2-security`, `policy_version`, document_count,
  created_at, sealed и immutable security_report (миграция 0030). Запечатать поколение можно только при совпадении count.
- `search_documents`: repository/snapshot/generation, document_id, entity_id,
  document_type, content (JSON), content_sha256, provenance (JSON). Составные FK
  запрещают смешивание repository/snapshot и потерю ссылки на исходную сущность.
  ID документа совместим с `project`; hash — SHA-256 канонического JSON content
  (UTF-8, sort_keys, compact separators), **отличается** от текстового хеша `project`.
- `search_index_publications`: один generation pointer на repository/snapshot.
  Только sealed generation разрешена к публикации. Запись документов sealed
  generation и изменение её метаданных запрещены; TRUNCATE запрещён. Удаление
  generation/snapshot каскадно удаляет производные строки.

Проекция, COPY, проверка полноты и CAS pointer выполняются одной транзакцией.
Неполное поколение не становится видимым. Ошибка SQL, политики или отмена
откатывают сборку, сохраняя прежнее поколение; повторный запуск безопасен с тем
же expected pointer. UUID новой сборки меняется, document_id и hashes одинаковы
при одинаковых фактах, projection version и детерминированной политике.
При изменении формата нужно менять PROJECTION_VERSION; при изменении политики —
policy_version. Смена одной версии без изменения текста не обязана менять hash.

`content` разделяет `title`, `summary`, `target_language` (en), `source_language`,
`path` и `redacted_source`. SQL/ORM query source удалён из summary и SQL title;
он сохраняется отдельно только после redaction. Для остальных видов source=null.
Политика вызывается также для заголовков, путей, summary и строк provenance,
включая Evidence descriptions и причины. Политика должна возвращать строки,
сохранять структурные идентификаторы/статусы и быть детерминированной.
Встроенная политика A06 обязательна до и после дополнительного caller redactor;
последний и его непустая версия по-прежнему передаются явно. Сохранённая
policy_version объединяет версию/режим A06 и версию caller policy. Изменение
структурных IDs/enum-статусов callback запрещено; его исключения маскируются.
Сырые source blobs не копируются. Детектор не является универсальным: см.
[source-data-security.md](source-data-security.md).

`provenance` сохраняет originating entity_id, source_range и относящиеся к
сущности Relation (source, target или candidate), с исходными resolution,
certainty, Evidence и Coverage. Reader добавляет repository/snapshot/generation.
Новые доказательства или зависимости не выводятся; PARTIAL/AMBIGUOUS/UNRESOLVED
и INFERRED сохраняются. ORM mapping/query status остаётся в summary.

`read_search_documents(conn, repository_id, *, allowed_repository_ids,
snapshot_id=None, after_document_id="", limit=100) -> list[dict]` одним SQL
закрепляет текущую UCM publication и полное search generation именно этого
snapshot. Если указан snapshot_id, он должен совпадать с текущей publication.
Нет publication/поколения или snapshot уже сменился — `LookupError`; пустое
полное поколение или конец страницы — `[]`. Старый snapshot не подставляется.
Результат содержит generation metadata, content/hash и provenance.

Пагинация: document_id ascending, `1 <= limit <= 1000`; передавать последний ID
в after_document_id. Для нескольких страниц или compound read использовать
read-only REPEATABLE READ (как canonical reader), иначе каждый вызов закрепляет
своё поколение. Для одной страницы достаточно одного SQL.

Оба API проверяют membership repository_id в **обязательном**
allowed_repository_ids до чтения БД; отказ — PermissionError. Набор разрешений
получает доверенный сервис из контекста авторизации, не из пользовательского
MCP-аргумента. Это внутренний API для доверенного DB connection; он не заменяет
HTTP authentication или RLS; A02 проверяет identity и права MCP до SQL. MCP остаётся read-only и пока не
экспортирует этот API. Пересборку вызывает управляющий процесс, не MCP.

C12 storage rebuild читает bounded neighborhoods; чистый `project(entities)` и
явный `load_snapshot_batch` сохраняют прежний batch-контракт и материализуют вход. Поколения не создаются
автоматически при canonical indexing; явная пересборка нужна для каждого нового
snapshot. Политика retention поколений и embeddings не входят в C01.

Проверки: `tests/test_search_storage.py` и
`tests/integration/test_search_document_storage.py`: deterministic rebuild,
ORM/SQL/symbol provenance, redaction, full/incremental reuse, repository/snapshot
isolation, denied access, CAS competition, pinned pagination, пустые поколения,
SQL rollback и отмена во время публикации на PostgreSQL 15.

## A06: protected derivatives

Public `project` masks supported secret patterns by default, adds a `redaction`
report and keeps canonical IDs and machine status/certainty unchanged. SQL titles
no longer contain truncated source literals. Textual hashes refer to masked text.
`security_policy=SecretPolicy("mask"|"skip"|"reject")` is a keyword-only option for
project and rebuild. C01 applies baseline scanning to both content and provenance,
including raw-context known values after caller redaction. Per-document metadata
lives in provenance.redaction, separate from original analysis Coverage.

Migration 0030 adds generation security_report: redacted/skipped counts, detector
categories and up to 256 skipped entity IDs with a truncation flag. The field is
immutable after sealing and removed with its generation.
`read_search_security_report(conn, repository_id, *, allowed_repository_ids)` reads
current-generation diagnostics even when every document was skipped. Both this
API and document reader authorize before DB access.

Readers reject legacy projection versions and unsafe stored content with a generic
rebuild-required error; existing sealed generations and canonical publications are
never rewritten. Rebuild with the new version to make derivatives readable.
`data_security.embedding_input(content)` rechecks C01 content before producing
future model input. No model/vector pipeline is added. Detector limits, false
positives, unrecognized secret forms and retention are documented in the A06 guide.

## C12: bounded storage rebuild

Public signatures, `PROJECTION_VERSION`, document IDs, JSON content hashes,
provenance and A06/caller redaction are unchanged. Storage rebuild no longer calls
`load_snapshot_batch`: keyset pages select at most 128 document-producing entities,
then hydrate only their direct relations (including candidate provenance), SQL
accesses, execution owners, call labels and source files. Every hydration SQL page
also contains at most 128 entity IDs. Parameter/local symbols and other fact kinds
are not roots, but remain available when needed as context. No graph inference or
certainty promotion occurs.

Formatting workspace is bounded to 8,192 canonical context entities. A root page
that exceeds it is split recursively in ID order; an oversized single document
fails the entire rebuild. Related facts are never truncated. One encoded record
and one COPY chunk are limited to 4 MiB UTF-8; exceeding this fails closed. These
are storage-rebuild capacity bounds, not changes to canonical UCM validity. As in
B02, a single canonical entity/nested payload is not given an absolute byte bound
before hydration; the limits prevent accumulation proportional to independent
facts, not arbitrary payload amplification inside one fact. `project` remains an
unrestricted pure batch formatter for compatibility.

Rows are staged in a session-owned temporary table in bounded COPY chunks. This
preserves the existing immutable generation metadata contract: final document count
and aggregate security report are known before inserting the unsealed generation.
INSERT SELECT, count-checked sealing and CAS publication use the same transaction;
staging is never reader-visible and disappears at commit/rollback/cancellation.
No migration or new durable table is needed. Generation diagnostics merge page
counts/categories and retain the same first 256 skipped entity IDs in the same
order with the same truncation flag. A cancelled CPU worker stops between documents
and is joined before releasing the snapshot lease or transaction.

Authorization still precedes every source query and policy call. The writer pins
the selected immutable snapshot before reading facts, so concurrent GC skips it.
READY and RETIRED sources remain valid for explicit offline builds. At the final
short repository lock, both the expected search-generation pointer and the original
canonical publication pointer must still match. A concurrent canonical publication
therefore rolls back the build instead of publishing stale work. This additional
CAS precondition can raise ValueError even when the per-snapshot search pointer
has not changed; retry explicitly against the intended version.

Regression coverage compares complete records and security reports against the
batch formatter with tiny pages, all six document kinds, skipped-ID truncation,
full/incremental reuse, candidate provenance, source-policy failures, partial COPY
errors, cancellation, lease/GC and concurrent publication. The opt-in
`python -m code_crawler.search_projection_benchmark` uses owned disposable PG15 DBs
and fresh batch/stream worker processes; no model or network service is called.
Default fixtures contain 141,431 and 1,000,011 canonical facts (10 facts/unit plus
one archived file), including an evidenced INFERRED call ring and non-document
candidate facts. Both modes hash all six persisted record fields in document-ID
order, including full contents and provenance. RSS is per-process high-water mark;
stream timing includes staging, persistence and atomic swap, while batch timing
includes full hydration and formatting but not persistence. They are memory/parity
evidence, not an isolated speed comparison or a production SLO.

```sh
BENCHMARK_DATABASE_URL=postgresql://.../postgres \
  uv run python -m code_crawler.search_projection_benchmark \
  --output /tmp/search-projection-pg15.json
```

Controlled scale results will be recorded after the verified implementation commit.
