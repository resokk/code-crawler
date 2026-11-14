# Design: Локальные embeddings, pgvector и кэш

## Context
В AGENTS.md модель эмбеддингов ещё не зафиксирована; сейчас нет persisted embeddings и pgvector retrieval.

## Proposed design
### Decision 1
Выбрать модель и размерность по русскому/английскому коду, нагрузке и лимитам pgvector 0.8.0; задокументировать benchmark вариантов.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 2
Создать search_embedding_models, search_embeddings, search_embedding_cache, generation/job tracking с model/preprocessing version.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 3
Вычислять векторы из redacted indexed documents, переиспользуя cache по content SHA и model key.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 4
Добавить HNSW по выбранной размерности, оценить фильтрацию snapshot/repository и fallback для отсутствующих embeddings.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

## Consistency and lifecycle
- Canonical UCM snapshots are immutable. Derived search documents, catalogs, embeddings and resolver caches carry snapshot/generation keys.
- Indexing one repository MUST NOT depend on another; remote references are resolved only at query-time.
- Published readers MUST see one coherent generation across one query or report explicit partial availability.
- No unauthorised access to repository source/evidence; default fail closed when auth is needed.

## Risks and recovery
Avoid unbounded search/fanout, wrong version selection and leakage of secrets via embeddings. A failed derivative generation leaves the previous published generation available. Forward migrations and PG15 tests are required for schema changes.

## Interfaces affected
src/code_crawler/migrations/; src/code_crawler/search_documents.py; src/code_crawler/; docs/; tests/

## Dependencies
C01,A06; model selection отдельный design decision
