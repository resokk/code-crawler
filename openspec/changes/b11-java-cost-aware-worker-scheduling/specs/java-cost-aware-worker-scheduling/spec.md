# Capability: java-cost-aware-worker-scheduling

## ADDED Requirements

### Requirement: Нет перекоса по тяжёлому файлу
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Нет перекоса по тяжёлому файлу
- **GIVEN** В одной группе есть один тяжёлый SQL файл и 31 лёгкий
- **WHEN** включён cost-aware scheduling при workers=2
- **THEN** задания распределены в рамках slice и длительность простаивания worker измерена

### Requirement: Последовательный режим остаётся быстрым
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Последовательный режим остаётся быстрым
- **GIVEN** В репозитории 8 маленьких Java файлов
- **WHEN** выбрана адаптивная стратегия с workers=4
- **THEN** она может выбрать последовательный путь без startup, не ухудшая семантику

### Requirement: Детерминированность фактов
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Детерминированность фактов
- **GIVEN** Разные worker возвращают результаты в другом порядке
- **WHEN** результаты собираются
- **THEN** UCM digest, diagnostics и SQL path report детерминированы и соответствуют workers=1

### Requirement: Ресурсная граница
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Ресурсная граница
- **GIVEN** Пришла пачка с большими файлами
- **WHEN** scheduler распределяет задачи
- **THEN** число in-flight files/bytes и процессов не превосходит явно установленный budget

### Requirement: Отмена
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Отмена
- **GIVEN** Один worker выходит с ошибкой
- **WHEN** индексирование отменяется
- **THEN** остальные workers/queues корректно закрываются, прежняя публикация остаётся доступной

### Requirement: Conservative regression policy
The feature MUST not compromise source identity, readiness, publication, cross-repository independence, or authorization to gain speed.

#### Scenario: Failure during optimized indexing
- **GIVEN** there is a previously published snapshot and an indexing task using this optimization
- **WHEN** the task fails, times out or is cancelled
- **THEN** the previous publication remains readable and incomplete facts are never published
