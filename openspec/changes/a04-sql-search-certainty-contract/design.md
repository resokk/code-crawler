# Design: Разграничение обнаружения SQL и доказанного execution в поиске

## Context and current implementation
Существующий readers/writers API выдаёт найденные SQL accesses и список executions; потребитель может трактовать отсутствие execution как доказанную запись.

## Proposed solution
### Decision 1
Определить typed output contract: discovery_status, execution_link_status, target_resolution, evidence/certainty отдельно.

### Decision 2
Для бездоказательного SQL сохранить found statement, но выставлять execution_link_status=NOT_ESTABLISHED.

### Decision 3
Для execution sink без восстановленного SQL предоставить execution record с пустым statements и явным coverage.

### Decision 4
Не менять семантику сохранённых UCM relations и не повышать certainty из-за текстового совпадения.

### Decision 5
Обновить docstrings MCP и примеры безопасных ответов агентам.

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
src/code_crawler/search.py; src/code_crawler/server.py; tests/integration/test_structural_search.py; docs/structural-search.md; docs/server.md

## Dependencies
A03 желательно перед новыми поисковыми DTO
