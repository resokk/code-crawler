# Design: Нагрузочная проверка 100+ независимых репозиториев

## Background
Цель системы — сотни репозиториев; текущие tests преимущественно про один snapshot/repository.

## Architecture decisions
### 1. Создать workload генератор с 100+ repo keys, смешанными языками, конфликтами FQN и DB names.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 2. Нагрузить parallel ingest, publication CAS, reader queries и concurrent GC с ограниченными DB connections.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 3. Измерить P50/P95 reader latency, throughput indexing, lock waits, memory, WAL/disk и failure recovery.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 4. Проверить fairness jobs, tenant/repository isolation и отсутствие межрепозиторных FK.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

## Trade-offs
Prefer measured, reversible improvements to speculative rewrites. Keep PostgreSQL 15 and current async Python stack; do not assume availability of unlisted extensions. Separate canonical data from derivative data and preserve query-time-only cross-repo resolution.

## Failure and rollback
A failure must not change current publication. New DB structures require new forward migration; no editing of already applied migrations. Benchmark memory/latency/locks where the feature is performance related.

## Implementation impact
src/code_crawler/jobs.py; src/code_crawler/publication.py; src/code_crawler/query_benchmark.py; tests/integration/; docs/benchmarks/

## Dependencies
B01,B02,B03,B04
