# Tasks: Регрессионные тесты скорости и эффективности индексации

**Dependencies:** B09 and existing PG15 CI, B01 benchmark; остальные B10–B18 потребляют результаты.

- [ ] 1. Read current main and existing B01/B02/B03/B04 benchmarks; record verified baseline and stage boundaries.
- [ ] 2. Design the smallest backward-compatible implementation, resource limits and explicit fallback.
- [ ] 3. Implement and independently verify: Определить стабильные hash-pinned fixtures small/CPU-heavy/catalog-heavy/SQL-dense, mixed languages, no-change clone, DB stage transfer и validation; version-control форматы measurement output.
- [ ] 4. Implement and independently verify: Добавить в обычный CI быстрые детерминированные algorithmic guards (число reparse, catalog rebuild, clones, queue depth, row conversions, total normalization passes) и canonical digest parity без строгого wall-time threshold.
- [ ] 5. Implement and independently verify: Создать отдельный reproducible PG15 performance job на выделенном benchmark runner с CPU/memory/disk limits, 3–5 trials и median/distribution; без разрешения пользоваться production DB.
- [ ] 6. Implement and independently verify: Сравнивать с согласованным baseline данного железа, фиксировать CI SHA, versions и профили; threshold определять после измерения естественного разброса, различать warning vs blocking.
- [ ] 7. Implement and independently verify: Добавить безопасный rollback/advisory при превышении budget, report CPU/IO/WAL/RSS и last-complete-stage для cancel/disk guard/OOM signals (не называть SIGTERM OOM автоматически).
- [ ] 8. Given/When/Then test (including negative case): Детерминированный guard
- [ ] 9. Given/When/Then test (including negative case): Нет CI флапов
- [ ] 10. Given/When/Then test (including negative case): Performance regression
- [ ] 11. Given/When/Then test (including negative case): Parity with speed
- [ ] 12. Given/When/Then test (including negative case): Resource stop
- [ ] 13. Compare optimized versus baseline normalized UCM facts, Evidence, Coverage and Publication CAS; no false STATIC_PROVEN/RESOLVED facts.
- [ ] 14. Add PostgreSQL 15 integration/rollback tests for DB changes and fault injection for cancellation/invalid input.
- [ ] 15. Run reproducible CPU/wall/RSS/DB WAL/IO benchmarks, report multiple samples and regression risks.
- [ ] 16. Update docs and OpenSpec task statuses only after verified tests; run Ruff and mandatory PG15 CI.
- [ ] 17. Archive completed change with exact SHA, test receipts and benchmark; never delete its specifications.
