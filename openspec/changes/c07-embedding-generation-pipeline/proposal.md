# Proposal: Локальные embeddings, pgvector и кэш

## Why
В AGENTS.md модель эмбеддингов ещё не зафиксирована; сейчас нет persisted embeddings и pgvector retrieval.

## Outcome
Локальные embeddings, pgvector и кэш. Выбрать модель и размерность по русскому/английскому коду, нагрузке и лимитам pgvector 0.8.0; задокументировать benchmark вариантов. Создать search_embedding_models, search_embeddings, search_embedding_cache, generation/job tracking с model/preprocessing version. Вычислять векторы из redacted indexed documents, переиспользуя cache по content SHA и model key. Добавить HNSW по выбранной размерности, оценить фильтрацию snapshot/repository и fallback для отсутствующих embeddings.

## Scope
- Выбрать модель и размерность по русскому/английскому коду, нагрузке и лимитам pgvector 0.8.0; задокументировать benchmark вариантов.
- Создать search_embedding_models, search_embeddings, search_embedding_cache, generation/job tracking с model/preprocessing version.
- Вычислять векторы из redacted indexed documents, переиспользуя cache по content SHA и model key.
- Добавить HNSW по выбранной размерности, оценить фильтрацию snapshot/repository и fallback для отсутствующих embeddings.

## Non-goals
Не считать Qwen3-Embedding-0.6B безусловно утверждённым выбором и не отправлять приватный код внешнему API.

## Dependencies
C01,A06; model selection отдельный design decision

## Impacted code
src/code_crawler/migrations/; src/code_crawler/search_documents.py; src/code_crawler/; docs/; tests/

## Priority
P1
