# Capability: sql-search-certainty

## ADDED Requirements

### Requirement: Нет ложного выполнения
The system MUST определить typed output contract: discovery_status, execution_link_status, target_resolution, evidence/certainty отдельно.

#### Scenario: Нет ложного выполнения
- GIVEN Java метод лишь присвоил DELETE в строку
- WHEN ищут table_writers
- THEN найденный SQL не маркируется как confirmed execution.

### Requirement: Доказанный sink
The system MUST для бездоказательного SQL сохранить found statement, но выставлять execution_link_status=NOT_ESTABLISHED.

#### Scenario: Доказанный sink
- GIVEN обнаружен JDBC execute c привязанным SQL statement
- WHEN ищут table_writers
- THEN статус статической связи execution явен и содержит Evidence.

### Requirement: Неизвестный SQL sink
The system MUST для execution sink без восстановленного SQL предоставить execution record с пустым statements и явным coverage.

#### Scenario: Неизвестный SQL sink
- GIVEN JDBC execute получает динамический SQL, не восстановленный статически
- WHEN ищут SQL executions
- THEN sink виден, а отсутствие statements объяснено.

### Requirement: Различие DB resolution
The system MUST не менять семантику сохранённых UCM relations и не повышать certainty из-за текстового совпадения.

#### Scenario: Различие DB resolution
- GIVEN таблица не разрешена до DATABASE_OBJECT
- WHEN API возвращает доступ
- THEN target_resolution не маркируется RESOLVED.

## Cross-cutting Requirements

### Requirement: Snapshot isolation and explainability
The change MUST preserve repository-scoped immutable published UCM facts and return Evidence/Coverage/Resolution for inferred relations.

#### Scenario: Failure does not modify current publication
- GIVEN an existing published snapshot
- WHEN this feature encounters an invalid input or a storage error
- THEN the publication pointer and previously published facts remain unchanged
