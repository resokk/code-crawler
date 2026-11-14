# Design: Гибридный exact/FTS/vector/graph поиск

## Context
Есть exact structural и lexical search, но нет согласованного retrieval, который комбинирует идентификаторы, векторы и граф с доказательствами.

## Proposed design
### Decision 1
Реализовать независимые exact, FTS/trigram, vector candidate producers с общим фильтром repo/snapshot/ACL.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 2
Комбинировать результаты через настраиваемую RRF или понятный ranking с traceable component scores.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 3
Обогащать top candidates только bounded graph expansion с Evidence, certainty и coverage.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 4
Измерять retrieval quality на русском/английском наборе вопросов по schema+SQL+API, фиксировать метрики без выдуманных процентов.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

## Consistency and lifecycle
- Canonical UCM snapshots are immutable. Derived search documents, catalogs, embeddings and resolver caches carry snapshot/generation keys.
- Indexing one repository MUST NOT depend on another; remote references are resolved only at query-time.
- Published readers MUST see one coherent generation across one query or report explicit partial availability.
- No unauthorised access to repository source/evidence; default fail closed when auth is needed.

## Risks and recovery
Avoid unbounded search/fanout, wrong version selection and leakage of secrets via embeddings. A failed derivative generation leaves the previous published generation available. Forward migrations and PG15 tests are required for schema changes.

## Interfaces affected
src/code_crawler/search.py; src/code_crawler/server.py; src/code_crawler/migrations/; tests/integration/; docs/

## Dependencies
C01,C06,C07
