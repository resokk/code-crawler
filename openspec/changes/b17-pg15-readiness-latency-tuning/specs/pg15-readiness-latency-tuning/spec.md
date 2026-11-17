# Capability: pg15-readiness-latency-tuning

## ADDED Requirements

### Requirement: Validation parity
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Validation parity
- **GIVEN** В snapshot есть нарушенный relation, SQL origin и scope cycle
- **WHEN** работает optimized readiness
- **THEN** все нарушения обнаруживаются теми же классами правил, READY не выставляется

### Requirement: Bounded heap
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Bounded heap
- **GIVEN** Число SQL фактов вырастает в четыре раза
- **WHEN** validation выполняется
- **THEN** проходит критерий B02 bounded heap, без возвращения all-SQL Python collections

### Requirement: Temp database limits
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Temp database limits
- **GIVEN** Очень глубокая scope graph вызывает большие pointer doubling updates
- **WHEN** выполняется readiness
- **THEN** temp storage и время измеряются; превышение лимита завершает валидацию без изменения publication pointer

### Requirement: Concurrent state
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Concurrent state
- **GIVEN** Во время validation другой процесс меняет lifecycle snapshot
- **WHEN** валидатор завершается
- **THEN** нет фиктивного READY receipt или смешанного источника фактов

### Requirement: Cold/warm plans
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Cold/warm plans
- **GIVEN** Два run используют разную степень прогрева
- **WHEN** сравнивают изменения
- **THEN** report различает холодный и тёплый кеш и не скрывает ухудшения одного из режимов

### Requirement: Performance claims require reproducible evidence
The change MUST NOT be called an improvement merely because one sample ran faster. Use fixed fixtures and record environment, algorithmic workload and full regression checks.

#### Scenario: Speed optimization changes semantics
- **GIVEN** a baseline UCM snapshot with exact canonical digest and Evidence
- **WHEN** an optimized mode produces an incompatible graph or invalid readiness receipt
- **THEN** acceptance fails even if wall time decreases
