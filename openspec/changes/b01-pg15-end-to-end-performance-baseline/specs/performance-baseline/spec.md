# Capability: performance-baseline

## ADDED Requirements

### Requirement: Замеры привязаны к commit и окружению
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Замеры привязаны к commit и окружению
- GIVEN Отчёт включает SHA, PG15 version, описание fixtures и независимые показатели каждой стадии.
- WHEN the feature is exercised
- THEN Отчёт включает SHA, PG15 version, описание fixtures и независимые показатели каждой стадии.

### Requirement: Стабильность результатов
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Стабильность результатов
- GIVEN Повтор 400-file fixture предоставляет distribution, а не единственный удачный замер.
- WHEN the feature is exercised
- THEN Повтор 400-file fixture предоставляет distribution, а не единственный удачный замер.

### Requirement: Большой масштаб
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Большой масштаб
- GIVEN Попытка >1 млн сущностей приводит к успеху либо документированному failure с последней стадией и измерениями.
- WHEN the feature is exercised
- THEN Попытка >1 млн сущностей приводит к успеху либо документированному failure с последней стадией и измерениями.

### Requirement: Безопасность benchmark
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Безопасность benchmark
- GIVEN Benchmark создаёт только собственные временные Git fixtures/DB; prod snapshots не меняются.
- WHEN the feature is exercised
- THEN Benchmark создаёт только собственные временные Git fixtures/DB; prod snapshots не меняются.

### Requirement: Snapshot integrity
The system MUST preserve published snapshot immutability, deterministic evidence and transparent partial coverage.

#### Scenario: Failure during feature execution
- GIVEN a previously published repository snapshot
- WHEN this change encounters an invalid fact, cancellation or PostgreSQL error
- THEN the published snapshot stays readable and no false RESOLVED facts are introduced
