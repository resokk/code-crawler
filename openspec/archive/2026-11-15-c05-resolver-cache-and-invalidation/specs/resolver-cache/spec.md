# Capability: resolver-cache

## ADDED Requirements

### Requirement: Freshness
The system MUST implement: Задать cache key: ExternalReference selector hash, context fingerprint, discovery generation и resolver algorithm version.

#### Scenario: Freshness
- GIVEN repo B опубликовал новый snapshot
- WHEN запрос повторён
- THEN старый RESOLVED cache entry не используется в новом контексте.

### Requirement: Изоляция контекстов
The system MUST implement: Хранить candidates и resolution с TTL/limits, provenance и однозначными reasons.

#### Scenario: Изоляция контекстов
- GIVEN pinned и deployment contexts различаются
- WHEN запросы обращаются к одному ExternalReference
- THEN ответы и cache keys не смешиваются.

### Requirement: Неавторитетный кэш
The system MUST implement: При изменении publication pointers или generation инвалидация должна вытекать из ключей; старые кэши не показывать.

#### Scenario: Неавторитетный кэш
- GIVEN кэш удалён
- WHEN запрос выполняется
- THEN исходные UCM и discovery позволяют пересоздать результат.

### Requirement: Соревнование поколений
The system MUST implement: Добавить bounded cache size, instrumentation hit/miss, race-safe generation reads.

#### Scenario: Соревнование поколений
- GIVEN generation меняется во время запроса
- WHEN resolver завершает
- THEN ответ соответствует одной зафиксированной версии.

### Requirement: Explicit provenance and uncertainty
Every derived search result MUST preserve source snapshot, originating UCM entity and distinguish RESOLVED, AMBIGUOUS and UNRESOLVED; similarity alone MUST NOT establish a definite code dependency.

#### Scenario: Insufficient evidence
- GIVEN a candidate matches only by name or semantic similarity
- WHEN retrieval returns it
- THEN it is a candidate, not a proven cross-repository relationship
