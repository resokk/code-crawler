# Design: Масштабируемая очистка больших snapshots

## Background
GC работает через DELETE множества строк и триггеров; на больших snapshots время и удержание locks неизвестны.

## Architecture decisions
### 1. Измерить GC WALL, locks, WAL, dead tuples и bloat на 100k/1M facts.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 2. Рассмотреть безопасное batch-deletion в управляемом графе таблиц; защитить CAS от удаления pinned/active references.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 3. Добавить lifecycle cleanup для orphan source blobs и derived search generations с учётом retention.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 4. Сохранить retry после crash и отчет количеств удалённых сущностей/байт.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

## Trade-offs
Prefer measured, reversible improvements to speculative rewrites. Keep PostgreSQL 15 and current async Python stack; do not assume availability of unlisted extensions. Separate canonical data from derivative data and preserve query-time-only cross-repo resolution.

## Failure and rollback
A failure must not change current publication. New DB structures require new forward migration; no editing of already applied migrations. Benchmark memory/latency/locks where the feature is performance related.

## Implementation impact
src/code_crawler/jobs.py; src/code_crawler/migrations/; tests/integration/test_ingest_jobs.py; docs/ingest-jobs.md

## Dependencies
A01,B01
