# Tasks

- [x] До реализации описать semantic contract в docs/sql-semantics.md.
- [x] Добавить SqlStatement/DataAccess/SqlIdentifier и semantic registry pairs.
- [x] Разбирать statements независимо, сохраняя decoded slices и error/unsupported statuses.
- [x] Сохранить quoted parts и explicit postgres/mysql/tsql profiles.
- [x] Учесть lexical CTE/subqueries, source aliases и unknown/ambiguous columns.
- [x] Разделить INSERT/UPDATE/DELETE/MERGE/UPSERT/DDL targets и read operands.
- [x] Исключить guessed effects для partial/dynamic constructions.
- [x] Связать execution sites со statements только через construction origins.
- [x] Добавить migration 0010, normalized names/reasons и readiness invariants.
- [x] Добавить semantic incremental profile и index_java_semantic.
- [x] Проверить 35 SQL unit, 8 Java adapter unit и 2 PostgreSQL integration tests.
- [x] Обновить UCM/schema/storage/indexing docs; Ruff/format/diff без ошибок.
- [x] Итоговый полный PostgreSQL 15 suite: 524 passed.
