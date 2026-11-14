# Design: Точный поиск SQL-доступов в контексте физической БД

## Context and current implementation
search._accesses фильтрует по нормализованным SQL-именам, не по database_key/version_key/DATABASE_OBJECT; одноимённые таблицы из разных БД смешиваются.

## Proposed solution
### Decision 1
Существующий API поиска по table/column оставить как синтаксический с явным mode в ответе.

### Decision 2
Добавить параметры database_key, schema_version_key и database_object_id, валидировать совместимую комбинацию.

### Decision 3
Точный режим строить по RESOLVES_DATABASE_OBJECT/DatabaseAccess с проверкой контекста snapshot и schema version.

### Decision 4
Не включать UNRESOLVED или AMBIGUOUS в группу точных физических совпадений; вернуть их отдельно либо явно отразить coverage.

### Decision 5
Индексировать часто используемые фильтры после EXPLAIN на PG15.

## Integration and compatibility
- Reuse canonical UCM entities, immutable published snapshots and existing migration/adapter contracts.
- Keep existing public APIs compatible unless this change explicitly requires a versioned extension.
- Do not resolve cross-repository links during ingestion; expose deferred candidates only at query time.
- Every inferred relationship must retain Resolution, Coverage and Evidence; do not promote UNKNOWN to STATIC_PROVEN.

## Alternatives and trade-offs
- Avoid a broad rewrite or introducing a parallel storage model; targeted updates are easier to verify and roll back.
- If an optimization weakens referential integrity or snapshot immutability, reject it and preserve the current behavior.

## Failure modes and recovery
- Fail closed for invalid input, unknown ownership or missing permissions; report diagnostics without leaking source bytes.
- Database modifications require migration, backward-compatibility review and integration tests on PostgreSQL 15.
- A failed operation MUST leave the previously published snapshot readable and unchanged.

## Implementation surfaces
src/code_crawler/search.py; src/code_crawler/server.py; src/code_crawler/database_resolution.py; tests/integration/test_structural_search.py; docs/structural-search.md

## Dependencies
Существующие database identity и structural search
