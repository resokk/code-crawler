# Tasks

- [x] До реализации описать execution contract и coverage в docs/sql-execution.md.
- [x] Добавить SqlExecute и EXECUTES_SQL/USES_SQL_CONSTRUCTION registry pairs.
- [x] Распознавать typed JDBC/Spring sinks без name-only promotion.
- [x] Разделить preparation и execution, сохранить local prepared origins/aliases.
- [x] Учесть reassignment, close, unknown-call/field escape и branch candidates.
- [x] Сохранить CALL scope, ordered argument Values, invocation/preparation Evidence.
- [x] Добавить migration 0009, normalized ingestion и readiness restore/validation.
- [x] Добавить incremental execution profile и opt-in index_java_execution.
- [x] Проверить 24 unit и 2 PostgreSQL integration tests.
- [x] Обновить UCM/schema/storage/indexing docs; Ruff/format/diff без ошибок.
- [x] Итоговый полный PostgreSQL 15 suite: 463 passed.
