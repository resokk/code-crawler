# Структурный поиск

Change `structural-search-api` плана [2.0](development-plan-v2.md): модуль
`code_crawler.search` — read-only запросы по фактам UCM. Это библиотечный API;
MCP-инструменты поверх него — отдельный change.

## Общие правила

- Scope — один репозиторий по `repository_key`, только его опубликованный snapshot.
  Нет публикации — `ValueError`. BUILDING/READY/RETIRED версии не читаются.
- `limit` от 1 до 200. Ответ: `{"snapshot_id", "items", "truncated"}`;
  `truncated=true` значит, что результатов больше, чем возвращено.
- Ничего не достраивается: возвращаются только сохранённые факты. Неразрешённые и
  неоднозначные связи не отбрасываются, а приходят с `resolution`, `reason` и
  `candidates`.
- Каждая связь несёт `certainty`, `coverage` (capability, версия, status, reasons)
  и `evidence` (path, строки и byte columns, analyzer, rule, description).
- Сущность описывается как id, type, name; для символов — kind, qualified_name,
  parameter_types; path и строки — если у сущности есть место в исходниках.

## Функции

| Функция | Что возвращает |
| --- | --- |
| `search_symbols(conn, key, name, *, kind, parameter_types, limit)` | символы с точным простым или полным именем; `parameter_types` сравнивается со списком имён типов параметров целиком |
| `find_callers(conn, key, symbol_id, *, limit)` | связи CALLS, где символ — target или один из candidates |
| `find_callees(conn, key, symbol_id, *, limit)` | связи CALLS из символа; у UNRESOLVED `target` равен null |
| `find_sql_executions(conn, key, *, symbol_id, limit)` | SQL execution sinks (api, owner, место) и их statements через EXECUTES_STATEMENT |
| `find_table_readers(conn, key, table, *, column, schema, limit)` | DATA_ACCESS с access_kind READ, statement и executions |
| `find_table_writers(...)` | то же для INSERT, UPDATE, DELETE, MERGE, DDL |
| `trace_dependency(conn, key, entity_id, *, direction, relation_kinds, depth, limit)` | связи на расстоянии до `depth` (1–6) от сущности, с полем `depth` |
| `get_evidence(conn, key, relation_id)` | одну связь с endpoints, Evidence, Coverage и candidates |

Имена таблиц, колонок и схем сравниваются с нормализованными именами SQL-анализа:
в режиме SYNTACTIC_NAME подходит имя как есть или в нижнем регистре. Без `column` ищутся accesses уровня
TABLE, с `column` — уровня COLUMN.

Пустой `statements` у execution значит, что SQL-текст sink статически не
восстановлен. Пустой `executions` у access значит, что SQL найден в коде, но его
выполнение не доказано.

`trace_dependency` идёт по RESOLVED связям; `direction="out"` — от source к target,
`"in"` — обратно. Неразрешённые связи достигнутых узлов возвращаются при обходе
наружу, но дальше по ним обход не идёт. Циклы ограничены глубиной.

## Ограничения

- Поиск имени точный и регистрозависимый; нечёткий — в
  [lexical-search.md](lexical-search.md).
- Нет фильтра по пути или языку внутри репозитория и нет постраничного курсора:
  только `limit` и `truncated`.
- У неразрешённого вызова нет имени цели; место вызова есть в `evidence`.
- Планы запросов, индексы и baseline latency: [query-indexes.md](query-indexes.md).

Для полных typed UCM entities (включая SQL bindings) и compound read закреплённой
публикации используется [canonical-read.md](canonical-read.md). Проекции этого
модуля сохраняют прежний контракт; внутри published_reader transaction их запросы
также видят один MVCC snapshot. get_evidence здесь возвращает метаданные связи;
точные archived source bytes восстанавливает typed reader.

Межрепозиторный `trace_cross_repository` использует явный C03 context и доверенные
repository grants. Контракт C06, лимиты и правила неопределённости:
[cross-repository-graph.md](cross-repository-graph.md).

## Контракт уверенности SQL (A04)

Расширение совместимо с прежними полями и аргументами; UCM и схема БД не меняются.
Новые поля `SqlSearchStatus` отделяют три независимых утверждения:

| Поле | Значения и смысл |
| --- | --- |
| `discovery_status` | `FOUND`: обнаружен SQL access либо execution sink |
| `execution_link_status` | `STATIC_PROVEN`: существует сохранённая RESOLVED связь с STATIC_PROVEN certainty; `INFERRED`: существует INFERRED связь; `NOT_ESTABLISHED`: статическая связь не доказана |
| `target_resolution` | у access — сохранённое `resolution` DB-цели; у sink — `NOT_APPLICABLE`, поскольку sink сам по себе не определяет таблицу |

У access статус execution относится к связи statement → sink (EXECUTES_STATEMENT
хранится в направлении sink → statement). Каждый элемент `executions` сохраняет
старое поле `certainty` и добавляет полную `relation` с Evidence и Coverage.
`access_relations` содержит доказательства самого SQL access, независимо от execution.
У sink статус относится к EXECUTES_SQL; `sink_relations` возвращает эти связи целиком.
Связи statement остаются в `statements[].relation`, их certainty не повышается.
`statement_relations` включает также неразрешённые связи, чтобы сохранять причины
неизвестного SQL и исходные Coverage/Evidence при пустом `statements`.

У sink `coverage` агрегирует неполноту возвращённых связей; отсутствие statements
всегда даёт PARTIAL: `SQL_TEXT_NOT_RECOVERED`, либо
`SQL_STATEMENT_LINK_NOT_RESOLVED`, если сохранены только кандидаты. Исходные capability,
analyzer version, status и reasons доступны в каждой relation. Это покрытие
статического анализа, не гарантия полноты runtime поведения.

Безопасные формулировки ответа агентом:

- FOUND + NOT_ESTABLISHED: «Найден DELETE для таблицы; связь с execution sink не установлена».
- STATIC_PROVEN: «Статически установлена связь SQL с JDBC sink; Evidence указывает место в исходнике».
- Пустой statements: «Обнаружен SQL sink, текст SQL не восстановлен».
- target_resolution=UNRESOLVED: «Имя таблицы найдено в SQL, конкретный DATABASE_OBJECT не разрешён».

Ни один статус не доказывает, что запрос действительно выполнялся при запуске приложения.
## Database-qualified SQL access search (A03)

Both `find_table_readers` and `find_table_writers` retain the existing positional
`table` argument and syntactic behavior. The response now always includes `mode`:

- `SYNTACTIC_NAME` (default): table is required; the previous normalized-name
  comparison is preserved. These are SQL syntax matches across any connection
  context in the selected repository snapshot. Physical selectors are rejected.
- `RESOLVED_DATABASE_OBJECT`: requires either `database_key` +
  `schema_version_key` + table, or a `database_object_id`. There is no implicit
  latest schema version and no automatic mode selection from supplied parameters.

```python
await find_table_readers(
    conn,
    "org/app",
    "users",
    mode="RESOLVED_DATABASE_OBJECT",
    database_key="orders-prod",
    schema_version_key="release-1",
    schema="public",
)
await find_table_writers(
    conn,
    "org/app",
    mode="RESOLVED_DATABASE_OBJECT",
    database_object_id=object_id,
)
```

`database_object_id` is a canonical snapshot-local DATABASE_OBJECT UCM entity ID
(`ucm:<64 hex>`), not a global `db:` object_key. It must identify a projected
TABLE/VIEW/MATERIALIZED_VIEW/FOREIGN_TABLE/COLUMN in the currently selected code
snapshot. A column ID implies column mode; a table ID cannot be combined with a
column. Other supplied identifiers/keys must agree exactly with the object.
Unknown, foreign-repository, unprojected-old-version or incompatible IDs fail with
ValueError. A database/version selector that has no resolved matching access
returns an empty page without probing global inventory for existence.

An object ID selects **physical identity** (`object_key`), including every file's
projection of that object in the selected snapshot, rather than matching only the
one file-owned UCM ID. Database/version must be supplied together; either can be
omitted only when both are derived from the object ID. Without an ID, `schema` is
an optional exact filter; different resolved schemas remain distinct in results.
With column omitted, only table-level accesses are returned; with column supplied,
only that physical column is returned.

Physical identifiers are actual stored names, case-sensitive, without `lower()` or
SQL quote parsing: use table="Users", column="ID" for SQL `"Users"."ID"`.
Literal quote characters are not stripped. Database/version keys are opaque exact
strings. All values are parameterized; malformed modes, invalid key combinations,
empty/NUL identifiers and invalid limits are rejected. The original syntactic
comparison intentionally retains its older as-is/lower behavior.

### Proof and incomplete availability

Exact mode joins only stored RESOLVED RESOLVES_DATABASE_OBJECT relations through
DatabaseAccess, its DatabaseContext and DatabaseObject. All joins carry the pinned
code snapshot; context database/version/fingerprint must equal the target object.
PARTIAL, AMBIGUOUS and UNRESOLVED relations, including matching candidates and
unassigned connections, never become exact matches. No resolver or analyzer is
run by the query.

One exact item represents a contextual DatabaseAccess. It retains the existing
syntactic fields and adds:

- `database_access_id`: contextual access identity.
- `database_object`: local database_object_id, global object_key, database_key,
  version_key, schema_fingerprint, actual catalog/schema/table/column and physical
  database_object_kind.
- `database_context`: context_id, connection_key and database/version/fingerprint.
- `database_relation`: original relation with its RESOLVED status, unchanged
  certainty, Coverage and Evidence. The existing item `resolution`/`reason` fields
  remain those of the syntactic DataAccess; physical resolution is explicitly in
  database_relation and must not be conflated with syntactic binding.

Executions in exact mode are restricted to the contextual access's own execution
and its stored EXECUTES_STATEMENT link, so shared SQL text cannot attach execution
sinks from another connection/database. Empty executions remain possible; physical
identity is not proof of SQL execution. A04 execution-certainty classification is preserved. In exact mode
`target_resolution` is the physical relation status; syntactic mode keeps its
original unresolved target status. Access/sink/statement relation proofs and
`discovery_status`/`execution_link_status` remain independent of physical identity.

The exact response also has conservative PARTIAL `coverage` with explicit
`excluded_resolutions` and reasons. This reports the restriction to known physical
bindings rather than silently claiming full coverage of unresolved code. No
excluded-row count or guessed candidate match is fabricated. `limit`/`truncated`
retain their existing meaning and deterministic ordering is by contextual access
and relation ID.

Both modes read only the current published snapshot. For compound queries and
protection from concurrent GC, use an authorized published_reader or read-only
REPEATABLE READ transaction; MCP already does so and authorizes the repository
before lookup. Publication may change concurrently without mixing DB schema/code
versions inside the pinned view. No source fact or publication is written by search.
The existing MCP tools accept the same mode/selectors and preserve A02 authentication,
repository ACL and generic errors. They do not expose client-supplied grants.

### Migration and plan evidence

Migration 0030 adds `ucm_database_objects_search_idx` on snapshot, database/version,
actual names and object_key. Existing relation-target and entity PK indexes are
reused. The PG15 regression compares actual API results and EXPLAIN ANALYZE BUFFERS
before/after the migration on a fixed 3,010-object projection fixture.
[Captured plans](benchmarks/database-qualified-search-pg15.json) show object lookup
switching from repeated PK probes (36 shared hits) to the composite index (3 hits).
The index occupied 466,944 bytes including retained snapshot rows. Single warm
samples were 0.300/0.110 ms execution; these are plan evidence, not a latency SLA or
statistically controlled throughput claim. The artifact records baseline SHA,
PostgreSQL version, platform, buffer counts, loops and sort memory in full plans.

Acceptance: tests/test_database_search.py, tests/integration/test_database_qualified_search.py
and MCP tests cover modes, two databases/versions, exact quoted names, all file
projections, uncertain bindings, execution-context correlation, pinned publication,
foreign IDs, invalid combinations, ACL/error redaction and identical before/after
index results. No SQL analyzer or database identity facts are changed by A03.
