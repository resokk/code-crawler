# Tasks: Быстрый no-op при полностью неизменном опубликованном репозитории

**Dependencies:** B03 and existing incremental planner, snapshot/publication API; B09.

- [ ] 1. Read current main and existing B01/B02/B03/B04 benchmarks; record verified baseline and stage boundaries.
- [ ] 2. Design the smallest backward-compatible implementation, resource limits and explicit fallback.
- [ ] 3. Implement and independently verify: Определить строгий equivalence key: repo identity, source fingerprint, commit hash, branch, dirty state, language routing, adapter versions/fingerprints, SQL path budget, catalog/dependency manifest и selected DB schema/connection context.
- [ ] 4. Implement and independently verify: Добавить opt-in --reuse-unchanged-publication для CLI/service без смены текущих API default contracts; возвращать REUSED_CURRENT и уже опубликованный snapshot ID, не создавая новый snapshot/job source data.
- [ ] 5. Implement and independently verify: Сохранять existing flow, когда хоть один параметр семантики/контекста изменился, source HEAD обновился, content archive невалиден или publication pointer сменился.
- [ ] 6. Implement and independently verify: Добавить race-safe проверку publication pointer, managed permissions, retained pins и source fingerprint; при конфликте выполняется обычный CAS/new snapshot, а не произвольное reuse.
- [ ] 7. Implement and independently verify: Измерить повторную индексацию неизменённого repо на 400/1000 файлах с SQL schema contexts, сравнить wall/DB I/O и все reader results.
- [ ] 8. Given/When/Then test (including negative case): Полная эквивалентность
- [ ] 9. Given/When/Then test (including negative case): Source changed
- [ ] 10. Given/When/Then test (including negative case): Commit changed
- [ ] 11. Given/When/Then test (including negative case): Version changed
- [ ] 12. Given/When/Then test (including negative case): CAS race
- [ ] 13. Given/When/Then test (including negative case): No-op audit
- [ ] 14. Compare optimized versus baseline normalized UCM facts, Evidence, Coverage and Publication CAS; no false STATIC_PROVEN/RESOLVED facts.
- [ ] 15. Add PostgreSQL 15 integration/rollback tests for DB changes and fault injection for cancellation/invalid input.
- [ ] 16. Run reproducible CPU/wall/RSS/DB WAL/IO benchmarks, report multiple samples and regression risks.
- [ ] 17. Update docs and OpenSpec task statuses only after verified tests; run Ruff and mandatory PG15 CI.
- [ ] 18. Archive completed change with exact SHA, test receipts and benchmark; never delete its specifications.
