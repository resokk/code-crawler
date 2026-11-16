# Capability: source-data-security

## ADDED Requirements

### Requirement: Неизменяемость Evidence
The system MUST определить уровни данных raw source / evidence / search projection / embedding и правила доступа/retention.

#### Scenario: Неизменяемость Evidence
- GIVEN оригинальный исходник сохранён в архиве
- WHEN формируется редактированная проекция
- THEN оригинал остаётся доступен только авторизованному читателю.

### Requirement: Маскирование поисковых данных
The system MUST разделить сохранение неизменённого оригинала для authorised evidence и redacted поисковый документ.

#### Scenario: Маскирование поисковых данных
- GIVEN в SQL/Java встречается явный API token
- WHEN создаётся search document
- THEN значение токена не включается в документ и embedding input.

### Requirement: Неутечка через диагностику
The system MUST ввести консервативный secret detector с диагностикой и политикой reject/mask/skip без записи plaintext в logs.

#### Scenario: Неутечка через диагностику
- GIVEN детектор нашёл секрет
- WHEN выдаются ошибки/логи
- THEN они содержат позицию/категорию, но не значение секрета.

### Requirement: Доступ и retention
The system MUST при срабатывании исключать опасные spans из search_documents и embedding input; сохранять provenance/coverage redaction.

#### Scenario: Доступ и retention
- GIVEN repo B недоступен клиенту A
- WHEN клиент делает hybrid search
- THEN документы/векторы B не участвуют в выдаче.

## Cross-cutting Requirements

### Requirement: Snapshot isolation and explainability
The change MUST preserve repository-scoped immutable published UCM facts and return Evidence/Coverage/Resolution for inferred relations.

#### Scenario: Failure does not modify current publication
- GIVEN an existing published snapshot
- WHEN this feature encounters an invalid input or a storage error
- THEN the publication pointer and previously published facts remain unchanged

### Requirement: Security failures preserve the previous derivative publication
The system MUST abort a rejected, failed or unbounded redaction build without
changing canonical or search publication pointers.

#### Scenario: Reject policy detects a credential
- GIVEN a published search generation and immutable captured source bytes
- WHEN a replacement generation uses reject policy and detects a credential
- THEN the previous generation remains readable and source hashes are unchanged.

### Requirement: Skipped documents remain explainable
The system MUST store repository-scoped immutable generation diagnostics for skip
policy, without including matched values.

#### Scenario: Skip policy removes unsafe documents
- GIVEN projected documents contain a test-only token
- WHEN skip policy builds a generation
- THEN affected documents are omitted and security_report records partial coverage and counts.

### Requirement: Custom policy cannot bypass baseline protection
The system MUST scan before and after custom redaction, preserve machine facts
and reject unsafe legacy derivative generations until rebuilt.

#### Scenario: A custom callback reinserts an unlabelled detected secret
- GIVEN the initial payload has a labelled credential
- WHEN a callback removes its label and reinserts its value
- THEN the value is still absent from persisted content and embedding input.

#### Scenario: An old generation lacks current protection
- GIVEN a sealed legacy search generation
- WHEN the current reader requests it
- THEN it reports a generic rebuild requirement without returning unsafe content.
