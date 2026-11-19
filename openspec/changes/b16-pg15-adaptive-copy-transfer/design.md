# Design: Сокращение количества PostgreSQL COPY/INSERT/TRUNCATE и round-trip

## Current implementation
_stage и _transfer вызываются на каждую file slice с отдельными COPY для каждого типа фактов, INSERT SELECT и TRUNCATE per table. На 400 файлах baseline показывает 15.76 с transfer, 10.76 с FK; высокая частота маленьких операций может отнимать заметное время на PostgreSQL протокол/DDL/locks.

## Design decisions
### D1: Собрать count/latency/row-size для каждого COPY, INSERT SELECT, TRUNCATE, ANALYZ
Собрать count/latency/row-size для каждого COPY, INSERT SELECT, TRUNCATE, ANALYZE и deferred FK flush; выделить число маленьких таблиц и запросов per slice.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D2: Ввести bounded target row/byte budget для объединения слишком маленьких staged t
Ввести bounded target row/byte budget для объединения слишком маленьких staged transfers и явно ограничивать maximum batch для очень больших полей; сохранить текущий алгоритм как baseline.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D3: Переиспользовать temp staging tables и column order/transfer plans, не отключая 
Переиспользовать temp staging tables и column order/transfer plans, не отключая все FK и не меняя canonical immutable tables.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D4: Применять более редкие ANALYZE только там, где это подтверждено статистикой/plan
Применять более редкие ANALYZE только там, где это подтверждено статистикой/plans PG15; после массовой загрузки сохранить корректную deferred verification до commit.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D5: На PostgreSQL 15 сравнить 400/1000-file, high-table-count и SQL-dense fixtures, 
На PostgreSQL 15 сравнить 400/1000-file, high-table-count и SQL-dense fixtures, сохранив rollback при duplicate/ref error, отсутствие orphan staging и прежний publication pointer.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

## Constraints and trade-offs
- Keep immutable snapshots, readiness and CAS publication; do not weaken FK, SourceRange, Evidence or certainty.
- Respect repository and principal authorization, cache lifetime and redaction; outputs cannot expose raw SQL/secret values.
- No unrelated parser redesign or historical SQL migration edits. All PG15 schema changes use new forward-only migration.
- Compare with pinned baseline and record wall, CPU, RSS (parent/worker), spool/temp disk, PostgreSQL WAL/IO, normalized entity digests and Coverage.

## Failure and rollback
Cancel/crash/duplicate/partial data must not modify current published snapshot or expose incomplete search generation. Preserve a fallback path and do not activate by default if performance regresses.

## Code impact
src/code_crawler/ingestion.py; src/code_crawler/incremental.py; src/code_crawler/bulk_benchmark.py; src/code_crawler/migrations/ (только новые при необходимости); tests/integration/test_bulk_ingestion.py; docs/ucm-ingestion.md
