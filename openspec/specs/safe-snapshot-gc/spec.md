# Capability: safe-snapshot-gc

## Requirements

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

### Requirement: Schema and FK preflight
The system MUST serialize GC with managed migrations and reject pending or unknown
migrations, missing/wrongly typed managed snapshot columns, unsafe immediate FK
order, and unmanaged inbound FKs before reaping jobs or deleting facts.

#### Scenario: Unknown migration or missing managed table
- GIVEN pending/unknown migrations or a missing managed snapshot table
- WHEN GC runs
- THEN it fails during preflight with no changed jobs, facts or publication pointer.

#### Scenario: Unmanaged cascade or inheritance
- GIVEN a foreign table referencing UCM with ON DELETE CASCADE or inheriting a managed table
- WHEN GC runs
- THEN it rejects unknown ownership before any deletion and preserves foreign rows.

#### Scenario: Concurrent migration
- GIVEN a managed migration holds its advisory lock
- WHEN GC starts
- THEN it waits and checks the committed migration state after that lock is released.

### Requirement: Active snapshot leases
The system MUST skip snapshots held by a reader lease or a live ingest job and
skip repository/snapshot rows locked by concurrent lifecycle operations.

#### Scenario: Retired version remains in use
- GIVEN a RETIRED snapshot pinned by a read transaction or referenced by a live job
- WHEN GC runs
- THEN it reports the version as skipped; a later GC can collect it after release.

#### Scenario: Concurrent publication or validation
- GIVEN a repository or eligible snapshot row locked by another transaction
- WHEN GC runs
- THEN the busy object is skipped without changing the publication pointer.

### Requirement: Cancellation and safe reports
The system MUST roll back reaping and deletion together and report only committed
counts, with errors that exclude PostgreSQL source-row/DETAIL bytes.

#### Scenario: Cancellation after a partial delete
- GIVEN an in-progress GC that has deleted some fact rows
- WHEN its task is cancelled
- THEN rows and jobs are restored and transaction advisory leases are released.

#### Scenario: Mid-delete storage failure
- GIVEN a simulated FK failure after earlier tables have been deleted
- WHEN GC fails
- THEN its report has empty deleted-snapshot lists and counts, safe SQLSTATE diagnostics,
  and the original facts and publication pointer remain unchanged.
