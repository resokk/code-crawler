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
