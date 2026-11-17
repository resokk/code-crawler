# Design: Ускорение UCM normalization и сериализации spool

## Current implementation
incremental._spool_facts выполняет _inspect → recheck(FileAnalysis) → _rows → pickle.dump, а write-phase читает pickle.load; ingestion._stage дополнительно преобразует list[dict] в tuples для asyncpg.copy_records_to_table. Стоимость этих преобразований в процентах времени индексации не измерена отдельно.

## Design decisions
### D1: Профилировать отдельно strict validation/recheck, materialization UCM entities, 
Профилировать отдельно strict validation/recheck, materialization UCM entities, mapping entity→normalized row, pickle encode/decode, dict→tuple и asyncpg COPY; считать байты и rows.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D2: Сократить повторные преобразования в течение одного доверенного pipeline
Сократить повторные преобразования в течение одного доверенного pipeline: единый typed row schema/table column order и bounded iterator для spool и COPY вместо нескольких полных копий списков.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D3: Сохранить вызов всех проверок схемы и ссылочной целостности; если typed FileAnal
Сохранить вызов всех проверок схемы и ссылочной целостности; если typed FileAnalysis уже прошёл проверку, допускается только формально доказанное устранение дублирования, с негативными тестами на изменённые поля.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D4: Сохранить приватный spool, его транзакционную изоляцию, отсутствие внешнего untr
Сохранить приватный spool, его транзакционную изоляцию, отсутствие внешнего untrusted pickle interface и cleanup при cancel/crash.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D5: Сравнить CPU, RSS, spool_bytes, transfer rows, FK/check и canonical digest на 40
Сравнить CPU, RSS, spool_bytes, transfer rows, FK/check и canonical digest на 400/1000-file и mixed-language fixtures.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

## Constraints and trade-offs
- Keep immutable snapshots, readiness and CAS publication; do not weaken FK, SourceRange, Evidence or certainty.
- Respect repository and principal authorization, cache lifetime and redaction; outputs cannot expose raw SQL/secret values.
- No unrelated parser redesign or historical SQL migration edits. All PG15 schema changes use new forward-only migration.
- Compare with pinned baseline and record wall, CPU, RSS (parent/worker), spool/temp disk, PostgreSQL WAL/IO, normalized entity digests and Coverage.

## Failure and rollback
Cancel/crash/duplicate/partial data must not modify current published snapshot or expose incomplete search generation. Preserve a fallback path and do not activate by default if performance regresses.

## Code impact
src/code_crawler/incremental.py; src/code_crawler/ingestion.py; src/code_crawler/ucm.py; src/code_crawler/performance_baseline.py; tests/integration/test_incremental_indexing.py; tests/test_ingestion.py
