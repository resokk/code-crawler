# Tasks: Сокращение количества PostgreSQL COPY/INSERT/TRUNCATE и round-trip

**Dependencies:** B09, B04 already done, B05 будущая bounded streaming.

- [ ] 1. Read current main and existing B01/B02/B03/B04 benchmarks; record verified baseline and stage boundaries.
- [ ] 2. Design the smallest backward-compatible implementation, resource limits and explicit fallback.
- [ ] 3. Implement and independently verify: Собрать count/latency/row-size для каждого COPY, INSERT SELECT, TRUNCATE, ANALYZE и deferred FK flush; выделить число маленьких таблиц и запросов per slice.
- [ ] 4. Implement and independently verify: Ввести bounded target row/byte budget для объединения слишком маленьких staged transfers и явно ограничивать maximum batch для очень больших полей; сохранить текущий алгоритм как baseline.
- [ ] 5. Implement and independently verify: Переиспользовать temp staging tables и column order/transfer plans, не отключая все FK и не меняя canonical immutable tables.
- [ ] 6. Implement and independently verify: Применять более редкие ANALYZE только там, где это подтверждено статистикой/plans PG15; после массовой загрузки сохранить корректную deferred verification до commit.
- [ ] 7. Implement and independently verify: На PostgreSQL 15 сравнить 400/1000-file, high-table-count и SQL-dense fixtures, сохранив rollback при duplicate/ref error, отсутствие orphan staging и прежний publication pointer.
- [ ] 8. Given/When/Then test (including negative case): Меньше маленьких round trips
- [ ] 9. Given/When/Then test (including negative case): Forward references
- [ ] 10. Given/When/Then test (including negative case): Rollback
- [ ] 11. Given/When/Then test (including negative case): Same snapshot only
- [ ] 12. Given/When/Then test (including negative case): Planner stability
- [ ] 13. Compare optimized versus baseline normalized UCM facts, Evidence, Coverage and Publication CAS; no false STATIC_PROVEN/RESOLVED facts.
- [ ] 14. Add PostgreSQL 15 integration/rollback tests for DB changes and fault injection for cancellation/invalid input.
- [ ] 15. Run reproducible CPU/wall/RSS/DB WAL/IO benchmarks, report multiple samples and regression risks.
- [ ] 16. Update docs and OpenSpec task statuses only after verified tests; run Ruff and mandatory PG15 CI.
- [ ] 17. Archive completed change with exact SHA, test receipts and benchmark; never delete its specifications.
