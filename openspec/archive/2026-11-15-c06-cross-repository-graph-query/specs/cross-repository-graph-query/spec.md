# Capability: cross-repository-graph-query

## ADDED Requirements

### Requirement: Два репозитория
The system MUST implement: Обходить локальные Relations внутри snapshot; только при ExternalReference вызывать query-time resolver.

#### Scenario: Два репозитория
- GIVEN метод A вызывает external method B
- WHEN обход разрешён с version context
- THEN путь содержит оба repo snapshots и источники.

### Requirement: Ambiguous hop
The system MUST implement: Ввести depth, fanout, max nodes, max hops между repos, timeout/cancellation и total result cap.

#### Scenario: Ambiguous hop
- GIVEN ExternalReference имеет 2 кандидата
- WHEN обход выполняется
- THEN ни один не становится подтверждённым продолжением без явной политики, статус AMBIGUOUS сохранён.

### Requirement: Depth bound
The system MUST implement: Проводить авторизацию каждого repository scope до перехода; предотвращать циклы и сохранять порядок пути.

#### Scenario: Depth bound
- GIVEN граф содержит циклы A→B→A
- WHEN задан depth=3
- THEN traversal конечен и не превышает лимит.

### Requirement: ACL
The system MUST implement: Для каждого edge и remote hop возвращать source and target snapshot, Evidence, certainty, resolution, truncation.

#### Scenario: ACL
- GIVEN удалённая цель в недоступном репозитории
- WHEN traversal достигает её
- THEN содержимое и существование недоступной цели не раскрываются.

### Requirement: Explicit provenance and uncertainty
Every derived search result MUST preserve source snapshot, originating UCM entity and distinguish RESOLVED, AMBIGUOUS and UNRESOLVED; similarity alone MUST NOT establish a definite code dependency.

#### Scenario: Insufficient evidence
- GIVEN a candidate matches only by name or semantic similarity
- WHEN retrieval returns it
- THEN it is a candidate, not a proven cross-repository relationship
