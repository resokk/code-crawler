# Capability: bulk-load-fk-optimization

## ADDED Requirements

### Requirement: Корректность FK
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Корректность FK
- GIVEN dangling relation
- WHEN выполняется загрузка
- THEN вся транзакция отклоняется и snapshot пуст.

### Requirement: Контролируемая скорость
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Контролируемая скорость
- GIVEN workload 1M entities
- WHEN тест повторён
- THEN измеряется полное время, включая FK и validation, и согласованный бюджет соблюдается.

### Requirement: Независимость collation
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Независимость collation
- GIVEN quoted SQL identifier и UCM key
- WHEN миграция изменяет collation индексного ключа
- THEN бизнес-семантика имен SQL не меняется.

### Requirement: Возврат к прошлой версии
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Возврат к прошлой версии
- GIVEN предыдущие snapshots
- WHEN выполняется migration
- THEN их PK/FK, reader и rollback работают.

### Requirement: Snapshot integrity
The system MUST preserve published snapshot immutability, deterministic evidence and transparent partial coverage.

#### Scenario: Failure during feature execution
- GIVEN a previously published repository snapshot
- WHEN this change encounters an invalid fact, cancellation or PostgreSQL error
- THEN the published snapshot stays readable and no false RESOLVED facts are introduced
