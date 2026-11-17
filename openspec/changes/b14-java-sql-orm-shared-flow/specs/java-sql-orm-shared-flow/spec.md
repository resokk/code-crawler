# Capability: java-sql-orm-shared-flow

## ADDED Requirements

### Requirement: Результат SQL и ORM совпадает
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Результат SQL и ORM совпадает
- **GIVEN** Java method одновременно вызывает JDBC и EntityManager
- **WHEN** работает shared-read-only-input mode
- **THEN** SQL_EXECUTE, ORM_OPERATION и их relations/coverage совпадают со старым вариантом

### Requirement: Path budget
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Path budget
- **GIVEN** Метод достигает max_paths=256
- **WHEN** включён общий read-only summary
- **THEN** число retained paths и overflow report не теряются

### Requirement: Ambiguous dispatch
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Ambiguous dispatch
- **GIVEN** Вызов dynamic/overloaded и неоднозначен
- **WHEN** shared lookup используется
- **THEN** не появляется ложный RESOLVED target

### Requirement: Incremental parity
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Incremental parity
- **GIVEN** Изменён один Java method
- **WHEN** пересчитывается snapshot
- **THEN** full/incremental canonical semantic digest остаётся одинаковым

### Requirement: Conservative regression policy
The feature MUST not compromise source identity, readiness, publication, cross-repository independence, or authorization to gain speed.

#### Scenario: Failure during optimized indexing
- **GIVEN** there is a previously published snapshot and an indexing task using this optimization
- **WHEN** the task fails, times out or is cancelled
- **THEN** the previous publication remains readable and incomplete facts are never published
