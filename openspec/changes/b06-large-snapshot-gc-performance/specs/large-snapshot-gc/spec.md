# Capability: large-snapshot-gc

## ADDED Requirements

### Requirement: Нельзя удалять pinned
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Нельзя удалять pinned
- GIVEN snapshot закреплён пользовательским контекстом
- WHEN GC запускается
- THEN snapshot сохраняется.

### Requirement: Нет побочных удалений
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Нет побочных удалений
- GIVEN public содержит не-UCM таблицы
- WHEN GC выполняется
- THEN они не затронуты.

### Requirement: Устойчивость отказа
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Устойчивость отказа
- GIVEN процесс убит в середине GC
- WHEN запуск повторяют
- THEN целостность snapshot и publication сохраняется.

### Requirement: Измеренная стоимость
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Измеренная стоимость
- GIVEN 1M facts
- WHEN GC исполняется
- THEN измерены worst-case locks и WAL, а целевой budget оформлен.

### Requirement: Snapshot integrity
The system MUST preserve published snapshot immutability, deterministic evidence and transparent partial coverage.

#### Scenario: Failure during feature execution
- GIVEN a previously published repository snapshot
- WHEN this change encounters an invalid fact, cancellation or PostgreSQL error
- THEN the published snapshot stays readable and no false RESOLVED facts are introduced
