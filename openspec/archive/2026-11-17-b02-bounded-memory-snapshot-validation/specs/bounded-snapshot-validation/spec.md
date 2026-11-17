# Capability: bounded-snapshot-validation

## ADDED Requirements

### Requirement: Эквивалентность валидации
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Эквивалентность валидации
- GIVEN Для всех существующих fixtures новый validator принимает и отклоняет те же наборы фактов, что старый.
- WHEN the feature is exercised
- THEN Для всех существующих fixtures новый validator принимает и отклоняет те же наборы фактов, что старый.

### Requirement: Ограниченное потребление памяти
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Ограниченное потребление памяти
- GIVEN При росте числа фактов вчетверо пик памяти validation не растёт пропорционально набору моделей; порог фиксируется после B01.
- WHEN the feature is exercised
- THEN При росте числа фактов вчетверо пик памяти validation не растёт пропорционально набору моделей; порог фиксируется после B01.

### Requirement: Безопасная публикация
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Безопасная публикация
- GIVEN Snapshot с порванным Relation или неполным Evidence не получает READY/PUBLISHED.
- WHEN the feature is exercised
- THEN Snapshot с порванным Relation или неполным Evidence не получает READY/PUBLISHED.

### Requirement: Конкурентность
The system MUST satisfy the following behavior without changing published canonical facts unless explicitly specified.

#### Scenario: Конкурентность
- GIVEN Изменение snapshot state/публикации во время validation не создаёт фиктивный receipt.
- WHEN the feature is exercised
- THEN Изменение snapshot state/публикации во время validation не создаёт фиктивный receipt.

### Requirement: Snapshot integrity
The system MUST preserve published snapshot immutability, deterministic evidence and transparent partial coverage.

#### Scenario: Failure during feature execution
- GIVEN a previously published repository snapshot
- WHEN this change encounters an invalid fact, cancellation or PostgreSQL error
- THEN the published snapshot stays readable and no false RESOLVED facts are introduced
