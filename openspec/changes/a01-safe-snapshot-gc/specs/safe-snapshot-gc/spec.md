# Capability: safe-snapshot-gc

## ADDED Requirements

### Requirement: Только управляемые таблицы
The system MUST определить явный allowlist таблиц из управляемой схемы UCM/ingest/search/resolver; поддерживать его при каждой миграции.

#### Scenario: Только управляемые таблицы
- GIVEN в public есть сторонняя таблица с snapshot_id и совпадающим UUID
- WHEN запускают GC
- THEN её строки не изменяются.

### Requirement: Сохранность опубликованных данных
The system MUST в startup/GC preflight сравнивать allowlist с актуальными FK и snapshot-bearing таблицами; незнакомая таблица не должна удаляться по умолчанию.

#### Scenario: Сохранность опубликованных данных
- GIVEN snapshot PUBLISHED, READY или VALIDATING
- WHEN запускают GC
- THEN snapshot и его facts остаются неизменными.

### Requirement: Атомарность удаления
The system MUST проверять state и publication pointer под блокировкой; закреплённые/используемые snapshots оставлять нетронутыми.

#### Scenario: Атомарность удаления
- GIVEN FK или другой сбой на одной из таблиц
- WHEN запускают GC
- THEN вся операция откатывается и publication pointer остаётся прежним.

### Requirement: Прозрачность
The system MUST обрабатывать связные таблицы с контролируемым порядком/DEFERRED constraints, возвращать отчёт количества удалённых строк и ошибок.

#### Scenario: Прозрачность
- GIVEN разрешённая очистка RETIRED/BUILDING snapshot
- WHEN GC завершается
- THEN результат перечисляет удалённые snapshots и достаточную диагностическую информацию.

## Cross-cutting Requirements

### Requirement: Snapshot isolation and explainability
The change MUST preserve repository-scoped immutable published UCM facts and return Evidence/Coverage/Resolution for inferred relations.

#### Scenario: Failure does not modify current publication
- GIVEN an existing published snapshot
- WHEN this feature encounters an invalid input or a storage error
- THEN the publication pointer and previously published facts remain unchanged
