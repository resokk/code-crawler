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


## Resolved contract

Existing table/column APIs default to SYNTACTIC_NAME and add an explicit mode to
responses. Exact mode requires database_key/schema_version_key/table or a
snapshot-local UCM DATABASE_OBJECT ID; global object_key is returned as provenance,
not accepted as a repository-bypassing selector. IDs derive names/version and select
all local file projections of the same physical object_key. Conflicting selectors
and table-ID/column combinations are rejected. Actual stored identifier spelling
is compared directly; no SQL quote stripping or lower() occurs in physical mode.

The exact query joins DatabaseObject → RESOLVED RESOLVES_DATABASE_OBJECT →
DatabaseAccess → DatabaseContext → original DataAccess/SqlStatement. Every join
is constrained to the pinned published snapshot and matching database/version/
fingerprint. Uncertain/candidate relations never enter the physical result group.
Existing syntactic resolution/reason fields are preserved; physical proof is in
explicit database_relation with unchanged Evidence/Coverage/certainty. Executions
are correlated to each contextual access rather than all uses of shared SQL text.
Conservative response coverage explicitly lists excluded resolution states.

MCP uses the same selectors through existing A02 authorization before SQL, in a
read-only repeatable-read request. No new grants or global inventory lookup is
exposed. Invalid input/errors preserve facts/publication and remain generic at MCP.

Migration 0030 adds a composite physical lookup index after before/after PG15
EXPLAIN ANALYZE BUFFERS verification with 3010 projected objects. Existing relation
and entity indexes are reused. Full contract and captured plans are documented in
docs/structural-search.md and docs/benchmarks/database-qualified-search-pg15.json.
SQL analyzers and canonical database identity generation remain unchanged.


Concurrent A04 integration is preserved: discovery_status, execution_link_status,
access_relations, execution sink/statement proofs remain independent. Exact mode
sets target_resolution from the stored physical relation, while legacy syntactic
resolution/reason fields stay unchanged. Execution linkage is filtered in SQL to
page-specific contextual execution IDs; shared SQL cannot inflate certainty or
attach another connection's sink. The combined A03/A04 PG15 regression verifies
physical RESOLVED with execution INFERRED and retained original relation proofs.
