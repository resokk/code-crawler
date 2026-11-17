# Design: Снижение времени полной проверки readiness без роста памяти

## Current implementation
B02 устранил full SQL hydration, но готовность snapshot остаётся существенной частью end-to-end: B01 до последних изменений измерял 43.13с на 400 файлах и 130.87с на 1000. Readiness включает SQL global invariants, temporary parent/link projections, pointer doubling для scope cycles, model hydration по 2000 entities и LRU 20000. Нужны свежие PG15 планы и оптимизация времени при сохранении строгой проверки.

## Design decisions
### D1: Добавить per-invariant wall/CPU/SQL EXPLAIN BUFFERS для global identity, scope c
Добавить per-invariant wall/CPU/SQL EXPLAIN BUFFERS для global identity, scope cycle, SQL statement/variant/origin/binding/context, evidence, ORM и model-level checks; разделить server-time и Python hydration.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D2: Измерить влияние fetch size 2000, LRU 20000, temp table indexes, pointer-doublin
Измерить влияние fetch size 2000, LRU 20000, temp table indexes, pointer-doubling update count, работу join nested paths; выбрать точечные изменения на двух разных fixtures.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D3: Ускорять только SELECT/temporary projections/prefetch, подтверждённые benchmark,
Ускорять только SELECT/temporary projections/prefetch, подтверждённые benchmark, без отключения SQL checks, FK, Coverage и reference validator parity.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D4: Сохранить repeatable-read snapshot scan, lease, cancellation drain и atomic READ
Сохранить repeatable-read snapshot scan, lease, cancellation drain и atomic READY receipt; контролировать temp DB bytes и длительность MVCC view.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D5: Провести negative parity fixtures для corrupted SQL origin, duplicate producer, 
Провести negative parity fixtures для corrupted SQL origin, duplicate producer, cyclic scope, ORM/FK, missing source archive, ambiguous resolution и Unicode slicing.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

## Constraints and trade-offs
- Keep immutable snapshots, readiness and CAS publication; do not weaken FK, SourceRange, Evidence or certainty.
- Respect repository and principal authorization, cache lifetime and redaction; outputs cannot expose raw SQL/secret values.
- No unrelated parser redesign or historical SQL migration edits. All PG15 schema changes use new forward-only migration.
- Compare with pinned baseline and record wall, CPU, RSS (parent/worker), spool/temp disk, PostgreSQL WAL/IO, normalized entity digests and Coverage.

## Failure and rollback
Cancel/crash/duplicate/partial data must not modify current published snapshot or expose incomplete search generation. Preserve a fallback path and do not activate by default if performance regresses.

## Code impact
src/code_crawler/publication.py; src/code_crawler/snapshot_validation.py; src/code_crawler/reader.py; src/code_crawler/validation_benchmark.py; docs/snapshot-validation-invariants.md; tests/integration/test_bounded_validation.py
