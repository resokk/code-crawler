# Design: Безопасная очистка UCM snapshots

## Context and current implementation
До `cefc213` jobs._delete_snapshots() находил все public таблицы с snapshot_id. Явный реестр уже внедрён; A01 завершает runtime preflight, блокировки/leases, атомарность reaping и отчётность.

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

## Implemented contract (2026-11-15)

The explicit registry landed in `cefc213`; A01 adds the runtime safety gate and
transactional reporting. `collect_garbage` requires a free connection and validates
options before reaping jobs. It holds the migration advisory lock in shared mode,
requires all and only known migrations, checks UUID snapshot columns, inbound FKs,
and the deletion order of immediate/cascading references. Foreign tables without
UCM FKs are ignored and reported. Foreign inbound FKs and inheritance/partitioning
are rejected before any data changes; DELETE inheritance and cascade cannot extend
the allowlist implicitly.

Repository rows are locked before snapshot rows, matching publication lock order.
State, current pointers and RUNNING jobs are rechecked under those locks. Busy rows
are skipped. Snapshot readers use shared transaction advisory leases; GC obtains
an exclusive lease through try-lock. Typed published readers and search inside a
transaction (including MCP) participate; independent SQL readers must explicitly
pin before reading. Hash collisions only conservatively postpone collection.

Reaping and deletion commit or roll back together. Reaping uses transaction leases
and never reaps the same connection's live session-owned job. Cancellation releases
leases and rolls back partial deletes. The existing `reaped_jobs`, `building`,
`retired` lists are retained; `GCReport` adds per-table committed `deleted_rows`,
`skipped`, `skipped_repositories`, `ignored_tables`, and `errors`. `GCError.report`
and CLI JSON carry safe stage/type/SQLSTATE/constraint diagnostics. Rolled-back
operations report no committed deletions; PostgreSQL row/DETAIL messages are not
chained into CLI diagnostics.

No schema or migration changes are needed: this uses existing immutable-table
triggers, FK constraints and PostgreSQL advisory locks. No UCM facts, inferred
relations or analysis Coverage are created or modified. Operational limits and
reader participation are documented in docs/ingest-jobs.md.

The query benchmark intentionally exercises pre-0018 index schemas in a disposable
owned database. Its historical trial cleanup explicitly deletes only its own trial
UUID via the registry; current-schema trials use the full GC gate. `cleanup_mode`
labels that distinction so historical cleanup is not mistaken for operational GC.

## Integration with current main

Search publication pointers are removed before their generations. Sealed search
documents are deleted by the generation cascade; row counts include those
cascaded documents. Discovery entries precede their generations and UCM entities.
Resolver contexts and deployment bindings are retained owners, not GC-owned
tables: their snapshot FKs are explicitly recognized and selected snapshots
are excluded under the existing resolver retention advisory lock.
Historical benchmark cleanup remains confined to its disposable database and
explicit trial UUID; production preflight requires all known migrations.
