# Capability: short-transaction-indexing

## ADDED Requirements

### Requirement: Анализ вне write transaction
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Анализ вне write transaction
- GIVEN медленный анализ адаптера
- WHEN job работает
- THEN write transaction не остаётся открытой на всё время CPU-анализa.

### Requirement: Исходники изменились
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Исходники изменились
- GIVEN файл изменился после capture
- WHEN идёт commit
- THEN новый snapshot не публикуется.

### Requirement: Конкурентная публикация
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Конкурентная публикация
- GIVEN одновременно публикуется другой snapshot
- WHEN завершается index
- THEN CAS предотвращает замену свежего published pointer.

### Requirement: Отказ на staging
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Отказ на staging
- GIVEN ошибка stage/transfer
- WHEN работа прервана
- THEN не существует частично опубликованных facts.

### Requirement: Snapshot integrity
The system MUST preserve published snapshot immutability, deterministic evidence and transparent partial coverage.

#### Scenario: Failure during feature execution
- GIVEN a previously published repository snapshot
- WHEN this change encounters an invalid fact, cancellation or PostgreSQL error
- THEN the published snapshot stays readable and no false RESOLVED facts are introduced
