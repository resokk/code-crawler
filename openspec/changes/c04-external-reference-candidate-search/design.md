# Design: Разрешение кандидатов ExternalReference по запросу

## Context
ExternalReference хранит selector, hints и Evidence локально, но глобального query-time сопоставления с доказательствами пока нет.

## Proposed design
### Decision 1
Нормализовать selector-specific lookup (Symbol signature, DB identity, HTTP method/path/service, Kafka/BPMN IDs).

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 2
Фильтровать кандидатов выбранным resolver_context и compatibility constraints, с bounded fanout.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 3
Возвращать RESOLVED только при единственной доказанной совместимой цели; иначе AMBIGUOUS/PARTIAL/UNRESOLVED с reasons.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 4
Каждый кандидат связывать с его snapshot, source Evidence, rule и certainty; unknown framework semantics не повышать.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

## Consistency and lifecycle
- Canonical UCM snapshots are immutable. Derived search documents, catalogs, embeddings and resolver caches carry snapshot/generation keys.
- Indexing one repository MUST NOT depend on another; remote references are resolved only at query-time.
- Published readers MUST see one coherent generation across one query or report explicit partial availability.
- No unauthorised access to repository source/evidence; default fail closed when auth is needed.

## Risks and recovery
Avoid unbounded search/fanout, wrong version selection and leakage of secrets via embeddings. A failed derivative generation leaves the previous published generation available. Forward migrations and PG15 tests are required for schema changes.

## Interfaces affected
src/code_crawler/ucm.py; src/code_crawler/search.py; src/code_crawler/migrations/; tests/integration/; docs/

## Dependencies
C02,C03
