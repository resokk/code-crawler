# Capability: java-worker-catalog-reuse

## ADDED Requirements

### Requirement: Одна сериализация каталога
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Одна сериализация каталога
- **GIVEN** Родитель построил immutable lookup catalog
- **WHEN** запускаются четыре worker-процесса
- **THEN** полный исходный каталог не строится четыре раза, а каждый worker получает проверенную view с версией и fingerprint

### Requirement: Семантическая эквивалентность
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Семантическая эквивалентность
- **GIVEN** Есть дубликаты FQN, overloads и SQL construction
- **WHEN** сравнивается одно- и многопроцессный анализ
- **THEN** множество нормализованных UCM facts, Coverage, Evidence и digest совпадает

### Requirement: Ошибка worker
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Ошибка worker
- **GIVEN** Ребёнок завершился при загрузке каталога
- **WHEN** parent indexer обрабатывает сбой
- **THEN** нет частичной публикации, все процессы завершаются и ресурсы освобождаются

### Requirement: Рост ресурсов
The system MUST preserve canonical UCM correctness while implementing the measured optimization.

#### Scenario: Рост ресурсов
- **GIVEN** Catalog-heavy 32-file fixture запускается на 1/2/4 workers
- **WHEN** выполняется benchmark
- **THEN** пересоздание каталога, startup, IPC, sum RSS и wall измерены; если оптимизация регрессирует, fallback остаётся доступен

### Requirement: Conservative regression policy
The feature MUST not compromise source identity, readiness, publication, cross-repository independence, or authorization to gain speed.

#### Scenario: Failure during optimized indexing
- **GIVEN** there is a previously published snapshot and an indexing task using this optimization
- **WHEN** the task fails, times out or is cancelled
- **THEN** the previous publication remains readable and incomplete facts are never published
