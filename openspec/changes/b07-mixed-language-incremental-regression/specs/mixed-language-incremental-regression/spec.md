# Capability: mixed-language-incremental-regression

## ADDED Requirements

### Requirement: Независимый адаптер
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Независимый адаптер
- GIVEN изменился Java class без зависимости Groovy
- WHEN запускают incremental
- THEN Groovy/PLPlus не анализируются повторно.

### Requirement: Транзитивность
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Транзитивность
- GIVEN Groovy зависит от изменившегося Java-symbol
- WHEN обновляют snapshot
- THEN Groovy dependent анализируется повторно.

### Requirement: Обработка удаления
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Обработка удаления
- GIVEN удалён CFT/PLPlus source
- WHEN индексируют заново
- THEN stale facts отсутствуют, Evidence не указывают на удалённый файл.

### Requirement: Сравнение полного и инкрементального
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Сравнение полного и инкрементального
- GIVEN одна и та же конечная версия Git
- WHEN сравнивают full vs incremental
- THEN canonical results семантически идентичны.

### Requirement: Snapshot integrity
The system MUST preserve published snapshot immutability, deterministic evidence and transparent partial coverage.

#### Scenario: Failure during feature execution
- GIVEN a previously published repository snapshot
- WHEN this change encounters an invalid fact, cancellation or PostgreSQL error
- THEN the published snapshot stays readable and no false RESOLVED facts are introduced
