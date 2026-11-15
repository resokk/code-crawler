# Design: Ограниченный графовый обход между репозиториями

## Context
Текущий trace_dependency ограничен одним snapshot и не пересекает deferred ExternalReference.

## Proposed design
### Decision 1
Обходить локальные Relations внутри snapshot; только при ExternalReference вызывать query-time resolver.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 2
Ввести depth, fanout, max nodes, max hops между repos, timeout/cancellation и total result cap.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 3
Проводить авторизацию каждого repository scope до перехода; предотвращать циклы и сохранять порядок пути.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 4
Для каждого edge и remote hop возвращать source and target snapshot, Evidence, certainty, resolution, truncation.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

## Consistency and lifecycle
- Canonical UCM snapshots are immutable. Derived search documents, catalogs, embeddings and resolver caches carry snapshot/generation keys.
- Indexing one repository MUST NOT depend on another; remote references are resolved only at query-time.
- Published readers MUST see one coherent generation across one query or report explicit partial availability.
- No unauthorised access to repository source/evidence; default fail closed when auth is needed.

## Risks and recovery
Avoid unbounded search/fanout, wrong version selection and leakage of secrets via embeddings. A failed derivative generation leaves the previous published generation available. Forward migrations and PG15 tests are required for schema changes.

## Interfaces affected
src/code_crawler/search.py; src/code_crawler/server.py; src/code_crawler/reader.py; tests/integration/; docs/structural-search.md

## Dependencies
C03,C04,C05

## Implemented contract

See [cross-repository-graph.md](../../../docs/cross-repository-graph.md) for the
version-1 response and bounds. A per-request deterministic breadth-first queue
coordinates bounded SQL projections and C04/C05 calls in one read-only transaction.
Pareto depth/hop visit state stops dominated expansion; branch ancestors identify
cycles. No persisted graph or DDL is introduced. MCP grants come only from the
server configuration. Ambiguous and partial candidates are report-only.
