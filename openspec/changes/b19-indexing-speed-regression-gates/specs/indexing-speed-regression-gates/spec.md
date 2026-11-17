# Capability: indexing-speed-regression-gates

## ADDED Requirements

### Requirement: Детерминированный guard
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Детерминированный guard
- **GIVEN** Новый код повторно парсит Java файлы в 10 раз чаще без изменения facts
- **WHEN** запускается unit CI
- **THEN** число parse/rebuild операций превышает утверждённый algorithmic budget и тест сообщает об ухудшении

### Requirement: Нет CI флапов
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Нет CI флапов
- **GIVEN** Обычный GitHub runner загружен соседними задачами
- **WHEN** запускается PR CI
- **THEN** успех функциональных тестов не определяется единственным нестабильным wall-time порогом

### Requirement: Performance regression
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Performance regression
- **GIVEN** На выделенном PG15 runner индексирование заметно замедлилось сверх measured noise
- **WHEN** запускается performance suite
- **THEN** регрессия появляется в versioned report с workload/stage/root cause и не маскируется success flag

### Requirement: Parity with speed
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Parity with speed
- **GIVEN** Оптимизация заметно быстрее, но убирает SQL Evidence или меняет parse_status
- **WHEN** запускается guard
- **THEN** она отклоняется, несмотря на ускорение

### Requirement: Resource stop
The implementation MUST preserve canonical UCM, Evidence, Coverage and publication integrity while executing this optimization.

#### Scenario: Resource stop
- **GIVEN** Нагрузка не помещается в свободное место и supervisor останавливает worker
- **WHEN** отчёт формируется
- **THEN** status отражает disk guard/stopped, не записывает недостигнутые stages как 0

### Requirement: Performance claims require reproducible evidence
The change MUST NOT be called an improvement merely because one sample ran faster. Use fixed fixtures and record environment, algorithmic workload and full regression checks.

#### Scenario: Speed optimization changes semantics
- **GIVEN** a baseline UCM snapshot with exact canonical digest and Evidence
- **WHEN** an optimized mode produces an incompatible graph or invalid readiness receipt
- **THEN** acceptance fails even if wall time decreases
