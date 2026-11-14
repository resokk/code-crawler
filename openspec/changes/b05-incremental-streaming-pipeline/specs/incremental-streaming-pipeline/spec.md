# Capability: incremental-streaming-pipeline

## ADDED Requirements

### Requirement: Память не пропорциональна размеру snapshot
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Память не пропорциональна размеру snapshot
- GIVEN два fixtures по N и 4N entities
- WHEN анализируются одинаковыми bounded chunks
- THEN рост RSS контролируем и зафиксирован benchmark.

### Requirement: Данные без изменений
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Данные без изменений
- GIVEN нет изменённых tracked файлов
- WHEN запускают incremental
- THEN анализаторы не вызываются и переиспользование facts сохраняет граф побайтно.

### Requirement: Forward references
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Forward references
- GIVEN method references symbol из следующей порции
- WHEN сборка завершается
- THEN relation имеет корректную локальную цель.

### Requirement: Сбой не публикует
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Сбой не публикует
- GIVEN ошибка парсинга, DB, cancellation
- WHEN конвейер прерван
- THEN published pointer и validated archived sources остаются неизменными.

### Requirement: Snapshot integrity
The system MUST preserve published snapshot immutability, deterministic evidence and transparent partial coverage.

#### Scenario: Failure during feature execution
- GIVEN a previously published repository snapshot
- WHEN this change encounters an invalid fact, cancellation or PostgreSQL error
- THEN the published snapshot stays readable and no false RESOLVED facts are introduced
