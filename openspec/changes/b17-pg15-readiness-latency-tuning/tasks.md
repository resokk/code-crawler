# Tasks: Снижение времени полной проверки readiness без роста памяти

**Dependencies:** B09 и завершённая B02 bounded-memory-snapshot-validation.

- [ ] 1. Read current main and existing B01/B02/B03/B04 benchmarks; record verified baseline and stage boundaries.
- [ ] 2. Design the smallest backward-compatible implementation, resource limits and explicit fallback.
- [ ] 3. Implement and independently verify: Добавить per-invariant wall/CPU/SQL EXPLAIN BUFFERS для global identity, scope cycle, SQL statement/variant/origin/binding/context, evidence, ORM и model-level checks; разделить server-time и Python hydration.
- [ ] 4. Implement and independently verify: Измерить влияние fetch size 2000, LRU 20000, temp table indexes, pointer-doubling update count, работу join nested paths; выбрать точечные изменения на двух разных fixtures.
- [ ] 5. Implement and independently verify: Ускорять только SELECT/temporary projections/prefetch, подтверждённые benchmark, без отключения SQL checks, FK, Coverage и reference validator parity.
- [ ] 6. Implement and independently verify: Сохранить repeatable-read snapshot scan, lease, cancellation drain и atomic READY receipt; контролировать temp DB bytes и длительность MVCC view.
- [ ] 7. Implement and independently verify: Провести negative parity fixtures для corrupted SQL origin, duplicate producer, cyclic scope, ORM/FK, missing source archive, ambiguous resolution и Unicode slicing.
- [ ] 8. Given/When/Then test (including negative case): Validation parity
- [ ] 9. Given/When/Then test (including negative case): Bounded heap
- [ ] 10. Given/When/Then test (including negative case): Temp database limits
- [ ] 11. Given/When/Then test (including negative case): Concurrent state
- [ ] 12. Given/When/Then test (including negative case): Cold/warm plans
- [ ] 13. Compare optimized versus baseline normalized UCM facts, Evidence, Coverage and Publication CAS; no false STATIC_PROVEN/RESOLVED facts.
- [ ] 14. Add PostgreSQL 15 integration/rollback tests for DB changes and fault injection for cancellation/invalid input.
- [ ] 15. Run reproducible CPU/wall/RSS/DB WAL/IO benchmarks, report multiple samples and regression risks.
- [ ] 16. Update docs and OpenSpec task statuses only after verified tests; run Ruff and mandatory PG15 CI.
- [ ] 17. Archive completed change with exact SHA, test receipts and benchmark; never delete its specifications.
