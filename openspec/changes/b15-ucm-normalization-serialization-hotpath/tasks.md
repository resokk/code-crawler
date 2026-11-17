# Tasks: Ускорение UCM normalization и сериализации spool

**Dependencies:** B09; B03 already implemented; совместима с B05.

- [ ] 1. Read current main and existing B01/B02/B03/B04 benchmarks; record verified baseline and stage boundaries.
- [ ] 2. Design the smallest backward-compatible implementation, resource limits and explicit fallback.
- [ ] 3. Implement and independently verify: Профилировать отдельно strict validation/recheck, materialization UCM entities, mapping entity→normalized row, pickle encode/decode, dict→tuple и asyncpg COPY; считать байты и rows.
- [ ] 4. Implement and independently verify: Сократить повторные преобразования в течение одного доверенного pipeline: единый typed row schema/table column order и bounded iterator для spool и COPY вместо нескольких полных копий списков.
- [ ] 5. Implement and independently verify: Сохранить вызов всех проверок схемы и ссылочной целостности; если typed FileAnalysis уже прошёл проверку, допускается только формально доказанное устранение дублирования, с негативными тестами на изменённые поля.
- [ ] 6. Implement and independently verify: Сохранить приватный spool, его транзакционную изоляцию, отсутствие внешнего untrusted pickle interface и cleanup при cancel/crash.
- [ ] 7. Implement and independently verify: Сравнить CPU, RSS, spool_bytes, transfer rows, FK/check и canonical digest на 400/1000-file и mixed-language fixtures.
- [ ] 8. Given/When/Then test (including negative case): Факты эквивалентны
- [ ] 9. Given/When/Then test (including negative case): Invalid input rejection
- [ ] 10. Given/When/Then test (including negative case): Bounded spool
- [ ] 11. Given/When/Then test (including negative case): Fault atomicity
- [ ] 12. Given/When/Then test (including negative case): Typed row schema
- [ ] 13. Compare optimized versus baseline normalized UCM facts, Evidence, Coverage and Publication CAS; no false STATIC_PROVEN/RESOLVED facts.
- [ ] 14. Add PostgreSQL 15 integration/rollback tests for DB changes and fault injection for cancellation/invalid input.
- [ ] 15. Run reproducible CPU/wall/RSS/DB WAL/IO benchmarks, report multiple samples and regression risks.
- [ ] 16. Update docs and OpenSpec task statuses only after verified tests; run Ruff and mandatory PG15 CI.
- [ ] 17. Archive completed change with exact SHA, test receipts and benchmark; never delete its specifications.
