# Capability: java-ast-analysis-reuse

## ADDED Requirements

### Requirement: Parser reuse only when equivalent
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Parser reuse only when equivalent
- **GIVEN** Один source file обрабатывается Java + HTTP enrichment
- **WHEN** в трассировке обнаружен повтор parse для тех же bytes/профиля
- **THEN** повтор parse можно устранить без изменения SourceAnalysis, diagnostic и UCM digest

### Requirement: Инвалидация
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Инвалидация
- **GIVEN** Content SHA или Java parser version изменились
- **WHEN** попытка reuse
- **THEN** устаревший AST/lookup отклонён и файл разобран заново

### Requirement: Duplicates
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Duplicates
- **GIVEN** Есть два модуля с одинаковым FQN
- **WHEN** строится catalog и local calls
- **THEN** каталог не объединяет их, resolution остаётся прежним

### Requirement: Cancellation
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Cancellation
- **GIVEN** Обработка файла прервана
- **WHEN** вызван abort/cleanup
- **THEN** временные AST/cache объекты освобождены, публикация не затронута

### Requirement: Conservative regression policy
The feature MUST not compromise source identity, readiness, publication, cross-repository independence, or authorization to gain speed.

#### Scenario: Failure during optimized indexing
- **GIVEN** there is a previously published snapshot and an indexing task using this optimization
- **WHEN** the task fails, times out or is cancelled
- **THEN** the previous publication remains readable and incomplete facts are never published
