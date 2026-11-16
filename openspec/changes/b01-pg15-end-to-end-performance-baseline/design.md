# Design: Воспроизводимый baseline производительности PG15

## Background
В проекте есть замеры на 402 Java-файлах и 141424 сущностях, но нет контролируемого end-to-end baseline на актуальном SHA и большом snapshot.

## Architecture decisions
### 1. Зафиксировать версии PG15, Python, окружение, RAM/CPU, work_mem/shared_buffers, тип workload и commit SHA.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 2. Раздельно измерить capture, prepare, analyze, stage, transfer/FK, validation, publication, GC и reader queries.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 3. Собрать серии на 400, 1000 файлах и >1 млн UCM entities; failures и OOM документировать как результат, не скрывать.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 4. Сохранить RAM RSS, IO, WAL, запросы EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON), stats и воспроизводимый fixture generator.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

## Trade-offs
Prefer measured, reversible improvements to speculative rewrites. Keep PostgreSQL 15 and current async Python stack; do not assume availability of unlisted extensions. Separate canonical data from derivative data and preserve query-time-only cross-repo resolution.

## Failure and rollback
A failure must not change current publication. New DB structures require new forward migration; no editing of already applied migrations. Benchmark memory/latency/locks where the feature is performance related.

## Implementation impact
src/code_crawler/query_benchmark.py; docs/query-indexes.md; docs/benchmarks/; tests/integration/test_query_benchmark_storage.py

## Dependencies
A01 желательно

## Resolved measurement contract

The new opt-in `performance_baseline` module shares the deterministic Java/JDBC
fixture and actual reader-query profiler with `query_benchmark`, but initializes
the current schema from the start. Historical pre-index phases are not part of
this end-to-end baseline. Groups 199/499/1500 produce 400/1000/3002 files; entity
counts, rather than filename count alone, establish the >1M milestone.

Each trial runs in a fresh child process and a parent-owned random database.
The parent creates/drops only its own database, retains partial worker checkpoints
on timeout/signal exit, and continues the remaining scales. Worker exceptions
persist class and last stage without arbitrary error/DSN text. Python wrappers
observe real capture, prepare, analysis, staging, transfer, FK and archival calls;
production code and transactions are unchanged. B04 ANALYZE/deferred-FK work is
included in the FK phase. Index total and nested stages overlap explicitly.

RSS high-water marks, process CPU/page faults/IO, per-stage WAL deltas, PG settings,
database/relation statistics and full EXPLAIN plans are retained. Full run SHA,
dirty-tree state, environment/container limits, dependency hash and deterministic
fixture hash make attribution reviewable. WAL is cluster-wide and requires idle
server conditions. Failed/cancelled phases remain raw observations and never enter
successful-stage distributions; early completed phases of failed runs do.

GC uses an unpublished server-side incremental clone of the published reference,
not a full in-memory batch or deletion of the reference publication. Bounded GC
cancellation is followed by published pointer and reader-result verification.
No new schema, migration, dependency, production query or certainty promotion is
needed. Small deterministic positive, invalid-input, failure and timeout fixtures
run in PG15 CI; expensive scale runs are explicit evidence, not timing assertions.
