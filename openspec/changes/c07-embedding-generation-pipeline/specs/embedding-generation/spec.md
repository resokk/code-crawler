# Capability: embedding-generation

## ADDED Requirements

### Requirement: Determinism
The system MUST implement: Выбрать модель и размерность по русскому/английскому коду, нагрузке и лимитам pgvector 0.8.0; задокументировать benchmark вариантов.

#### Scenario: Determinism
- GIVEN документ не менялся
- WHEN переиндексируют без смены модели
- THEN embeddings берутся из cache, лишнего inference нет.

### Requirement: Model versioning
The system MUST implement: Создать search_embedding_models, search_embeddings, search_embedding_cache, generation/job tracking с model/preprocessing version.

#### Scenario: Model versioning
- GIVEN меняется preprocessing или модель
- WHEN строят embeddings
- THEN старые векторы не маркируются как новые.

### Requirement: Partial generation
The system MUST implement: Вычислять векторы из redacted indexed documents, переиспользуя cache по content SHA и model key.

#### Scenario: Partial generation
- GIVEN inference fail на части документов
- WHEN retrieval работает
- THEN generation явно PARTIAL и не подменяет authoritative UCM.

### Requirement: No exfiltration
The system MUST implement: Добавить HNSW по выбранной размерности, оценить фильтрацию snapshot/repository и fallback для отсутствующих embeddings.

#### Scenario: No exfiltration
- GIVEN source содержит secret
- WHEN embedding input формируется
- THEN секрет отсутствует в передаваемом модели тексте.

### Requirement: Explicit provenance and uncertainty
Every derived search result MUST preserve source snapshot, originating UCM entity and distinguish RESOLVED, AMBIGUOUS and UNRESOLVED; similarity alone MUST NOT establish a definite code dependency.

#### Scenario: Insufficient evidence
- GIVEN a candidate matches only by name or semantic similarity
- WHEN retrieval returns it
- THEN it is a candidate, not a proven cross-repository relationship
