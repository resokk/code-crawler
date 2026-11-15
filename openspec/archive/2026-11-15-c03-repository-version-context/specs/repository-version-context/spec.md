# Capability: repository-version-context

## ADDED Requirements

### Requirement: Pinned snapshots
The system MUST implement: Реализовать resolver_contexts с режимами LATEST_INDEXED, PINNED_SNAPSHOTS, DEPLOYMENT_CONTEXT и immutable selection manifest.

#### Scenario: Pinned snapshots
- GIVEN repo A и B закреплены на snapshots X,Y
- WHEN выполняют cross-repo поиск
- THEN другие версии A/B не участвуют.

### Requirement: Latest indexed
The system MUST implement: Для pinned проверять repo ownership, readiness и наличие retained snapshot; для deployment явное mapping service/deploy to snapshot.

#### Scenario: Latest indexed
- GIVEN новый published snapshot B
- WHEN LATEST_INDEXED query повторён
- THEN выбор B обновляется, кэш не подменяет старые результаты.

### Requirement: Deployment uncertainty
The system MUST implement: Разделить выбор версии, разрешение candidate и publication; missing versions и unknown deployments — явная ошибка/неопределённость.

#### Scenario: Deployment uncertainty
- GIVEN deployment mapping неизвестен
- WHEN выбран DEPLOYMENT_CONTEXT
- THEN нельзя молча использовать latest.

### Requirement: Retention
The system MUST implement: Включать context fingerprint в кэш и Evidence path; поддержать pin retention при GC.

#### Scenario: Retention
- GIVEN context с pinned retired snapshot
- WHEN работает GC
- THEN pinned версия не удаляется.

### Requirement: Explicit provenance and uncertainty
Every derived search result MUST preserve source snapshot, originating UCM entity and distinguish RESOLVED, AMBIGUOUS and UNRESOLVED; similarity alone MUST NOT establish a definite code dependency.

#### Scenario: Insufficient evidence
- GIVEN a candidate matches only by name or semantic similarity
- WHEN retrieval returns it
- THEN it is a candidate, not a proven cross-repository relationship
