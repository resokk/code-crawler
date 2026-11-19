# Capability: sqlglot-dialect-parse-cache

## ADDED Requirements

### Requirement: Кэш только точного запроса
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Кэш только точного запроса
- **GIVEN** Два identical SQL текста имеют один dialect и parser options
- **WHEN** проводится SQLGlot parse в одной сессии
- **THEN** повторная parse работа может быть переиспользована, а generated SQL facts/Evidence каждого исходника остаются отдельными

### Requirement: Диалекты изолированы
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Диалекты изолированы
- **GIVEN** Один SQL текст анализируется как PostgreSQL и Oracle
- **WHEN** проверяются cache keys
- **THEN** результаты и ошибки не смешиваются между dialects

### Requirement: Mutable AST safety
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Mutable AST safety
- **GIVEN** Один caller преобразует SQLGlot AST
- **WHEN** второй получает cached parse
- **THEN** первый не изменяет AST второго и SQL AST interpretations совпадают с uncached

### Requirement: Неизвестный SQL
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Неизвестный SQL
- **GIVEN** SQL statement incomplete или invalid
- **WHEN** кэш включён
- **THEN** parse_status, partial coverage и причины не превращаются в COMPLETE

### Requirement: Cache bound
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Cache bound
- **GIVEN** Unique SQL занимает больше LRU budget
- **WHEN** анализ продолжается
- **THEN** старые entry вытесняются, память контролируема, publication unaffected

### Requirement: Conservative regression policy
The feature MUST not compromise source identity, readiness, publication, cross-repository independence, or authorization to gain speed.

#### Scenario: Failure during optimized indexing
- **GIVEN** there is a previously published snapshot and an indexing task using this optimization
- **WHEN** the task fails, times out or is cancelled
- **THEN** the previous publication remains readable and incomplete facts are never published
