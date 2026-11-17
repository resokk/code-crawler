# Proposal: Регрессионные тесты скорости и эффективности индексации

**Priority:** P1

## Why
Текущие PG15 CI тесты проверяют корректность, но не фиксируют алгоритмическую регрессию скорости; локальные benchmark часто измерены по одному run, разные hosts/fixtures и иногда завершаются disk guard. После новых оптимизаций нужен устойчивый quality gate, не флапающий из-за общей нагрузки на GitHub Actions.

## Intended outcome
Сокращение измеренного времени индексации без изменения канонических UCM-фактов, публикации, покрытия, разрешения и Evidence.

## Scope
- Определить стабильные hash-pinned fixtures small/CPU-heavy/catalog-heavy/SQL-dense, mixed languages, no-change clone, DB stage transfer и validation; version-control форматы measurement output.
- Добавить в обычный CI быстрые детерминированные algorithmic guards (число reparse, catalog rebuild, clones, queue depth, row conversions, total normalization passes) и canonical digest parity без строгого wall-time threshold.
- Создать отдельный reproducible PG15 performance job на выделенном benchmark runner с CPU/memory/disk limits, 3–5 trials и median/distribution; без разрешения пользоваться production DB.
- Сравнивать с согласованным baseline данного железа, фиксировать CI SHA, versions и профили; threshold определять после измерения естественного разброса, различать warning vs blocking.
- Добавить безопасный rollback/advisory при превышении budget, report CPU/IO/WAL/RSS и last-complete-stage для cancel/disk guard/OOM signals (не называть SIGTERM OOM автоматически).

## Non-goals
- Не блокировать обычные PR на абсолютное время шумного общего GitHub runner.
- Не считать разовый локальный benchmark статистическим доказательством ускорения.
- Не заменять PostgreSQL integration tests microbench-only успехом.

## Dependencies
B09 and existing PG15 CI, B01 benchmark; остальные B10–B18 потребляют результаты.

## Affected code
.github/workflows/ci.yml; src/code_crawler/performance_baseline.py; src/code_crawler/parallel_benchmark.py; src/code_crawler/validation_benchmark.py; docs/performance-baseline.md; docs/benchmarks/; tests/test_performance_baseline.py

## Acceptance
- Стабильные small-CI algorithmic guards + отдельная PR/manual/scheduled performance suite с documented noise и reproducible PG15 settings.
- Все future performance OpenSpec ссылаются на одну версию benchmark contract.
