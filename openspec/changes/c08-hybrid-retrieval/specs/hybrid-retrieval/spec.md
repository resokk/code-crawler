# Capability: hybrid-retrieval

## ADDED Requirements

### Requirement: Exact priority
The system MUST implement: Реализовать независимые exact, FTS/trigram, vector candidate producers с общим фильтром repo/snapshot/ACL.

#### Scenario: Exact priority
- GIVEN запрос содержит точный FQN
- WHEN выполняют hybrid retrieval
- THEN exact entity не скрывается за нерелевантными похожими векторами.

### Requirement: Semantic non-proof
The system MUST implement: Комбинировать результаты через настраиваемую RRF или понятный ranking с traceable component scores.

#### Scenario: Semantic non-proof
- GIVEN два метода имеют похожие embeddings
- WHEN возвращаются candidates
- THEN CALLS между ними не создаётся автоматически.

### Requirement: Snapshot scope
The system MUST implement: Обогащать top candidates только bounded graph expansion с Evidence, certainty и coverage.

#### Scenario: Snapshot scope
- GIVEN selected pinned context
- WHEN ищут hybrid
- THEN в result нет документов других версий.

### Requirement: Explainable ranking
The system MUST implement: Измерять retrieval quality на русском/английском наборе вопросов по schema+SQL+API, фиксировать метрики без выдуманных процентов.

#### Scenario: Explainable ranking
- GIVEN найден результат
- WHEN клиент открывает его
- THEN доступны lexical/vector/structural contributors и evidence links.

### Requirement: Explicit provenance and uncertainty
Every derived search result MUST preserve source snapshot, originating UCM entity and distinguish RESOLVED, AMBIGUOUS and UNRESOLVED; similarity alone MUST NOT establish a definite code dependency.

#### Scenario: Insufficient evidence
- GIVEN a candidate matches only by name or semantic similarity
- WHEN retrieval returns it
- THEN it is a candidate, not a proven cross-repository relationship
