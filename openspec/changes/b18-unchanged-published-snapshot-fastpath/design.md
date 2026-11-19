# Design: Быстрый no-op при полностью неизменном опубликованном репозитории

## Current implementation
No-change incremental сейчас создаёт новый immutable BUILDING snapshot и server-side клонирует факты. По B01 400-файловый clone занимает ~33.47 с плюс дальнейшая валидация/публикация, хотя content/fingerprint могут быть идентичными. Для частых cron/CI переиндексаций нужен безошибочный, явный fast-path без потери семантики snapshot identity.

## Design decisions
### D1: Определить строгий equivalence key
Определить строгий equivalence key: repo identity, source fingerprint, commit hash, branch, dirty state, language routing, adapter versions/fingerprints, SQL path budget, catalog/dependency manifest и selected DB schema/connection context.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D2: Добавить opt-in --reuse-unchanged-publication для CLI/service без смены текущих 
Добавить opt-in --reuse-unchanged-publication для CLI/service без смены текущих API default contracts; возвращать REUSED_CURRENT и уже опубликованный snapshot ID, не создавая новый snapshot/job source data.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D3: Сохранять existing flow, когда хоть один параметр семантики/контекста изменился,
Сохранять existing flow, когда хоть один параметр семантики/контекста изменился, source HEAD обновился, content archive невалиден или publication pointer сменился.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D4: Добавить race-safe проверку publication pointer, managed permissions, retained p
Добавить race-safe проверку publication pointer, managed permissions, retained pins и source fingerprint; при конфликте выполняется обычный CAS/new snapshot, а не произвольное reuse.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

### D5: Измерить повторную индексацию неизменённого repо на 400/1000 файлах с SQL schema
Измерить повторную индексацию неизменённого repо на 400/1000 файлах с SQL schema contexts, сравнить wall/DB I/O и все reader results.

Treat this as a small, independently testable change against existing UCM APIs. Document execution boundary, resource budget, data ownership, concurrency and cancellation behavior. Benchmark before changing defaults.

## Constraints and trade-offs
- Keep immutable snapshots, readiness and CAS publication; do not weaken FK, SourceRange, Evidence or certainty.
- Respect repository and principal authorization, cache lifetime and redaction; outputs cannot expose raw SQL/secret values.
- No unrelated parser redesign or historical SQL migration edits. All PG15 schema changes use new forward-only migration.
- Compare with pinned baseline and record wall, CPU, RSS (parent/worker), spool/temp disk, PostgreSQL WAL/IO, normalized entity digests and Coverage.

## Failure and rollback
Cancel/crash/duplicate/partial data must not modify current published snapshot or expose incomplete search generation. Preserve a fallback path and do not activate by default if performance regresses.

## Code impact
src/code_crawler/cli.py; src/code_crawler/incremental.py; src/code_crawler/snapshots.py; src/code_crawler/jobs.py; tests/integration/test_default_index.py; tests/integration/test_incremental_indexing.py; docs/ucm-incremental.md
