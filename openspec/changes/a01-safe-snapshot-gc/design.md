# Design: Безопасная очистка UCM snapshots

## Context and current implementation
jobs._delete_snapshots() обнаруживает все таблицы public с колонкой snapshot_id и удаляет из них строки; посторонняя таблица может попасть в GC.

## Proposed solution
### Decision 1
Определить явный allowlist таблиц из управляемой схемы UCM/ingest/search/resolver; поддерживать его при каждой миграции.

### Decision 2
В startup/GC preflight сравнивать allowlist с актуальными FK и snapshot-bearing таблицами; незнакомая таблица не должна удаляться по умолчанию.

### Decision 3
Проверять state и publication pointer под блокировкой; закреплённые/используемые snapshots оставлять нетронутыми.

### Decision 4
Обрабатывать связные таблицы с контролируемым порядком/DEFERRED constraints, возвращать отчёт количества удалённых строк и ошибок.

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
src/code_crawler/jobs.py; src/code_crawler/migrations/; tests/integration/test_ingest_jobs.py; docs/ingest-jobs.md

## Dependencies
нет
