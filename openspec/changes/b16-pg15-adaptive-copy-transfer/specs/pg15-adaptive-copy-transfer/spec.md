# Capability: pg15-adaptive-copy-transfer

## ADDED Requirements

### Requirement: Меньше маленьких round trips
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Меньше маленьких round trips
- **GIVEN** Текущий fixture даёт много таблиц с 1–10 строками в каждом source slice
- **WHEN** включён adaptive transfer
- **THEN** число PostgreSQL команд сокращается при bounded stage, и integrity/typed FK полностью сохранены

### Requirement: Forward references
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Forward references
- **GIVEN** Relation ссылается на entity, которую перенесут позже
- **WHEN** выполняется adaptive COPY
- **THEN** relation становится валидной только после deferred FK check и публикация не прерывается из-за порядка

### Requirement: Rollback
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Rollback
- **GIVEN** Третий chunk нарушает FK или имеет duplicate entity ID
- **WHEN** выполняется transfer
- **THEN** все ранее внесённые rows данного BUILDING snapshot откатываются в одной атомарной write transaction

### Requirement: Same snapshot only
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Same snapshot only
- **GIVEN** Два репозитория индексируются одновременно
- **WHEN** открыты staging tables
- **THEN** temp tables и snapshot IDs не пересекаются между соединениями

### Requirement: Planner stability
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Planner stability
- **GIVEN** План FK lookup меняется после bulk staging
- **WHEN** заканчивается COPY
- **THEN** используется корректная свежая статистика и измерения показывают отсутствие catastrophic sequential-scan regression

### Requirement: Performance claims require reproducible evidence
The change MUST NOT be called an improvement merely because one sample ran faster. Use fixed fixtures and record environment, algorithmic workload and full regression checks.

#### Scenario: Speed optimization changes semantics
- **GIVEN** a baseline UCM snapshot with exact canonical digest and Evidence
- **WHEN** an optimized mode produces an incompatible graph or invalid readiness receipt
- **THEN** acceptance fails even if wall time decreases
