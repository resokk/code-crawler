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
