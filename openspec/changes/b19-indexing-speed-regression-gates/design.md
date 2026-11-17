# Design: Регрессионные тесты скорости и эффективности индексации

## Current implementation
Текущие PG15 CI тесты проверяют корректность, но не фиксируют алгоритмическую регрессию скорости; локальные benchmark часто измерены по одному run, разные hosts/fixtures и иногда завершаются disk guard. После новых оптимизаций нужен устойчивый quality gate, не флапающий из-за общей нагрузки на GitHub Actions.

## Design decisions
### D1: Определить стабильные hash-pinned fixtures small/CPU-heavy/catalog-heavy/SQL-den
Определить стабильные hash-pinned fixtures small/CPU-heavy/catalog-heavy/SQL-dense, mixed languages, no-change clone, DB stage transfer и validation; version-control форматы measurement output.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D2: Добавить в обычный CI быстрые детерминированные algorithmic guards (число repars
Добавить в обычный CI быстрые детерминированные algorithmic guards (число reparse, catalog rebuild, clones, queue depth, row conversions, total normalization passes) и canonical digest parity без строгого wall-time threshold.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D3: Создать отдельный reproducible PG15 performance job на выделенном benchmark runn
Создать отдельный reproducible PG15 performance job на выделенном benchmark runner с CPU/memory/disk limits, 3–5 trials и median/distribution; без разрешения пользоваться production DB.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D4: Сравнивать с согласованным baseline данного железа, фиксировать CI SHA, versions
Сравнивать с согласованным baseline данного железа, фиксировать CI SHA, versions и профили; threshold определять после измерения естественного разброса, различать warning vs blocking.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D5: Добавить безопасный rollback/advisory при превышении budget, report CPU/IO/WAL/R
Добавить безопасный rollback/advisory при превышении budget, report CPU/IO/WAL/RSS и last-complete-stage для cancel/disk guard/OOM signals (не называть SIGTERM OOM автоматически).

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

## Constraints and trade-offs
- Keep immutable snapshots, readiness and CAS publication; do not weaken FK, SourceRange, Evidence or certainty.
- Respect repository and principal authorization, cache lifetime and redaction; outputs cannot expose raw SQL/secret values.
- No unrelated parser redesign or historical SQL migration edits. All PG15 schema changes use new forward-only migration.
- Compare with pinned baseline and record wall, CPU, RSS (parent/worker), spool/temp disk, PostgreSQL WAL/IO, normalized entity digests and Coverage.

## Failure and rollback
Cancel/crash/duplicate/partial data must not modify current published snapshot or expose incomplete search generation. Preserve a fallback path and do not activate by default if performance regresses.

## Code impact
.github/workflows/ci.yml; src/code_crawler/performance_baseline.py; src/code_crawler/parallel_benchmark.py; src/code_crawler/validation_benchmark.py; docs/performance-baseline.md; docs/benchmarks/; tests/test_performance_baseline.py
