# Capability: global-discovery-catalog

## ADDED Requirements

### Requirement: Каталог неоднозначностей
The system MUST implement: Разработать search_discovery_entries с repository_id/snapshot_id, entity_id, kind, qualifier, normalized lookup keys и generation.

#### Scenario: Каталог неоднозначностей
- GIVEN два репозитория публикуют одинаковый Symbol FQN
- WHEN ищут ключ
- THEN каталог возвращает оба кандидата.

### Requirement: Published only
The system MUST implement: Проецировать только факты PUBLISHED и сохранять уникальность ключей без требования единственного глобального кандидата.

#### Scenario: Published only
- GIVEN BUILDING snapshot содержит API operation
- WHEN обновляется каталог
- THEN эта операция не видима глобальному поиску.

### Requirement: Точность ключей
The system MUST implement: Индексировать symbol FQN+signature, DB identifiers, HTTP route/service, worker/process, reference dataset и Kafka topic; неизвестные типы не выдумывать.

#### Scenario: Точность ключей
- GIVEN разные DB contexts или HTTP service key
- WHEN ключи сравниваются
- THEN они не схлопываются по простому имени.

### Requirement: Отмена публикации
The system MUST implement: Поддержать retire/GC/rollback/generation invalidation без переиндексации несвязанных репозиториев.

#### Scenario: Отмена публикации
- GIVEN published pointer переключён
- WHEN refresh каталога
- THEN старые entries отделены по snapshot/generation.

### Requirement: Explicit provenance and uncertainty
Every derived search result MUST preserve source snapshot, originating UCM entity and distinguish RESOLVED, AMBIGUOUS and UNRESOLVED; similarity alone MUST NOT establish a definite code dependency.

#### Scenario: Insufficient evidence
- GIVEN a candidate matches only by name or semantic similarity
- WHEN retrieval returns it
- THEN it is a candidate, not a proven cross-repository relationship
