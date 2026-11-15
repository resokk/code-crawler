# Capability: external-reference-candidate-search

## ADDED Requirements

### Requirement: Единственная цель
The system MUST implement: Нормализовать selector-specific lookup (Symbol signature, DB identity, HTTP method/path/service, Kafka/BPMN IDs).

#### Scenario: Единственная цель
- GIVEN selector и фиксированный контекст однозначно подтверждают одну цель
- WHEN resolver вызывают
- THEN status=RESOLVED и Evidence path доступен.

### Requirement: Два кандидата
The system MUST implement: Фильтровать кандидатов выбранным resolver_context и compatibility constraints, с bounded fanout.

#### Scenario: Два кандидата
- GIVEN два совместимых метода из двух модулей
- WHEN resolver вызывают
- THEN status=AMBIGUOUS, оба candidates сохранены.

### Requirement: Нет кандидата
The system MUST implement: Возвращать RESOLVED только при единственной доказанной совместимой цели; иначе AMBIGUOUS/PARTIAL/UNRESOLVED с reasons.

#### Scenario: Нет кандидата
- GIVEN отсутствует реализация внешней зависимости
- WHEN resolver вызывают
- THEN статус UNRESOLVED без ошибки ingest.

### Requirement: Превышен fanout
The system MUST implement: Каждый кандидат связывать с его snapshot, source Evidence, rule и certainty; unknown framework semantics не повышать.

#### Scenario: Превышен fanout
- GIVEN каталог содержит тысячи совпадений
- WHEN выполняют query
- THEN результат ограничен, помечен PARTIAL/truncated.

### Requirement: Explicit provenance and uncertainty
Every derived search result MUST preserve source snapshot, originating UCM entity and distinguish RESOLVED, AMBIGUOUS and UNRESOLVED; similarity alone MUST NOT establish a definite code dependency.

#### Scenario: Insufficient evidence
- GIVEN a candidate matches only by name or semantic similarity
- WHEN retrieval returns it
- THEN it is a candidate, not a proven cross-repository relationship
