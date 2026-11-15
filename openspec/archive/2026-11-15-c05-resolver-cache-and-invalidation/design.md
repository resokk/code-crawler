# Design: Кэш query-time разрешений с инвалидацией

## Context
Повторные lookup across hundreds repos затратны; кэш не должен выдавать устаревшие результаты после смены published generation.

## Proposed design
### Decision 1
Задать cache key: ExternalReference selector hash, context fingerprint, discovery generation и resolver algorithm version.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 2
Хранить candidates и resolution с TTL/limits, provenance и однозначными reasons.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 3
При изменении publication pointers или generation инвалидация должна вытекать из ключей; старые кэши не показывать.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 4
Добавить bounded cache size, instrumentation hit/miss, race-safe generation reads.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

## Consistency and lifecycle
- Canonical UCM snapshots are immutable. Derived search documents, catalogs, embeddings and resolver caches carry snapshot/generation keys.
- Indexing one repository MUST NOT depend on another; remote references are resolved only at query-time.
- Published readers MUST see one coherent generation across one query or report explicit partial availability.
- No unauthorised access to repository source/evidence; default fail closed when auth is needed.

## Risks and recovery
Avoid unbounded search/fanout, wrong version selection and leakage of secrets via embeddings. A failed derivative generation leaves the previous published generation available. Forward migrations and PG15 tests are required for schema changes.

## Interfaces affected
src/code_crawler/migrations/; src/code_crawler/search.py; src/code_crawler/publication.py; tests/integration/; docs/

## Dependencies
C02,C03,C04

## Implemented contract

The normative API, cache key, TTL/capacity bounds, read-only lifecycle and
verification rules are documented in [resolver-cache.md](../../../docs/resolver-cache.md).
The cache is filled by CLI/maintenance only; MCP misses recompute C04 without a
write, preserving AGENTS.md's read-only server contract. CandidateResolution is
unchanged; INFO events provide hit/miss/bypass instrumentation without shared worker
state. Snapshot/generation cascades and the explicit safe-GC registry remove stale
derivatives; context verification always precedes a hit.
