# Capability: ucm-normalization-serialization-hotpath

## ADDED Requirements

### Requirement: Факты эквивалентны
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Факты эквивалентны
- **GIVEN** Один UCM fixture даёт более миллиона normalized rows разных типов
- **WHEN** строится streaming normalized output
- **THEN** все table/column/value/ref и canonical fact digest совпадают с текущим loader

### Requirement: Invalid input rejection
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Invalid input rejection
- **GIVEN** После FileAnalysis construction изменена вложенная relation или SourceRange
- **WHEN** запускается optimized normalization
- **THEN** невалидный факт отклонён до публикации, несмотря на устранение промежуточных копий

### Requirement: Bounded spool
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Bounded spool
- **GIVEN** Отдельная entity содержит крупные, но разрешённые вложенные поля
- **WHEN** spool создаётся
- **THEN** memory/bytes budget учитывает реальный размер payload и не выделяет неограниченный список копий

### Requirement: Fault atomicity
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Fault atomicity
- **GIVEN** pickle/spool/tuple conversion вызывает исключение
- **WHEN** index job завершается
- **THEN** WRITE не начинает публиковать неполный snapshot, временные ресурсы освобождены

### Requirement: Typed row schema
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Typed row schema
- **GIVEN** Тип table имеет разные optional columns в разных slices
- **WHEN** COPY выполняется
- **THEN** колонки и значения остаются согласованы; не происходит silent null/value shift

### Requirement: Performance claims require reproducible evidence
The change MUST NOT be called an improvement merely because one sample ran faster. Use fixed fixtures and record environment, algorithmic workload and full regression checks.

#### Scenario: Speed optimization changes semantics
- **GIVEN** a baseline UCM snapshot with exact canonical digest and Evidence
- **WHEN** an optimized mode produces an incompatible graph or invalid readiness receipt
- **THEN** acceptance fails even if wall time decreases
