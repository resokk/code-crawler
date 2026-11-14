# Design: Глобальный каталог потенциальных целей

## Context
Сейчас search только repository-scoped; нет производных каталожных ключей для поиска внешних символов, API, Kafka, BPMN и DB resources.

## Proposed design
### Decision 1
Разработать search_discovery_entries с repository_id/snapshot_id, entity_id, kind, qualifier, normalized lookup keys и generation.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 2
Проецировать только факты PUBLISHED и сохранять уникальность ключей без требования единственного глобального кандидата.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 3
Индексировать symbol FQN+signature, DB identifiers, HTTP route/service, worker/process, reference dataset и Kafka topic; неизвестные типы не выдумывать.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 4
Поддержать retire/GC/rollback/generation invalidation без переиндексации несвязанных репозиториев.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

## Consistency and lifecycle
- Canonical UCM snapshots are immutable. Derived search documents, catalogs, embeddings and resolver caches carry snapshot/generation keys.
- Indexing one repository MUST NOT depend on another; remote references are resolved only at query-time.
- Published readers MUST see one coherent generation across one query or report explicit partial availability.
- No unauthorised access to repository source/evidence; default fail closed when auth is needed.

## Risks and recovery
Avoid unbounded search/fanout, wrong version selection and leakage of secrets via embeddings. A failed derivative generation leaves the previous published generation available. Forward migrations and PG15 tests are required for schema changes.

## Interfaces affected
src/code_crawler/migrations/; src/code_crawler/search.py; src/code_crawler/ucm.py; docs/; tests/integration/

## Dependencies
C01, C03 желательно
