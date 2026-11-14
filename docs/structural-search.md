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
подходит имя как есть или в нижнем регистре. Без `column` ищутся accesses уровня
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
