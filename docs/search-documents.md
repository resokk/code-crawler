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

Таблицы в `public`:

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

Ограничения: loader и project пока материализуют полный snapshot; B02 ещё не
закрыт, bounded-memory/миллион сущностей не заявлены. Поколения не создаются
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
