# Capability: indexing-critical-path-profiler

## ADDED Requirements

### Requirement: Корректные границы этапов
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Корректные границы этапов
- **GIVEN** Проект индексируется с Java SQL/ORM и PostgreSQL 15
- **WHEN** включён подробный benchmark
- **THEN** файл содержит capture, catalog, analyze, row conversion, spool, transfer, FK, validation, publish с unit/elapsed и указанием вложенности

### Requirement: Отсутствие смешивания CPU и ожидания
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Отсутствие смешивания CPU и ожидания
- **GIVEN** Запуск содержит SQL write и Python CPU
- **WHEN** строится критический путь
- **THEN** wall и CPU/IO ожидание различаются; сумма дочерних nested этапов не выдаётся за total

### Requirement: Параллельная память
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Параллельная память
- **GIVEN** Запущены два Java worker-процесса
- **WHEN** строится отчёт
- **THEN** измеряются память родителя и дочерних процессов, а возможное двойное считывание shared pages явно отмечается

### Requirement: Безопасный отчёт
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Безопасный отчёт
- **GIVEN** В исходниках присутствуют SQL credentials и пути
- **WHEN** профилировщик записывает JSON
- **THEN** секреты, тела SQL и source bytes отсутствуют; ошибки содержат только stage/status

### Requirement: Сбой нагрузки
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Сбой нагрузки
- **GIVEN** Нагрузочный worker остановлен из-за disk guard
- **WHEN** завершается benchmark
- **THEN** завершённые stages сохраняются, а незавершённые не маркируются нулевой длительностью

### Requirement: Conservative regression policy
The feature MUST not compromise source identity, readiness, publication, cross-repository independence, or authorization to gain speed.

#### Scenario: Failure during optimized indexing
- **GIVEN** there is a previously published snapshot and an indexing task using this optimization
- **WHEN** the task fails, times out or is cancelled
- **THEN** the previous publication remains readable and incomplete facts are never published
