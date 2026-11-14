# Design: Сквозная bounded-memory индексация

## Background
Analyzer по срезам и staging уже есть, server-side reuse добавлен; validation и источники некоторых адаптеров ещё используют большие модели.

## Architecture decisions
### 1. Ввести ограниченный in-flight budget по количеству entities/bytes, а не только файлов; считать max size per file.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 2. Использовать stream API с staged writes и server-side clone unchanged facts без объединения в полный UcmBatch.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 3. Гарантировать cross-file references, forward references, deterministic ownership/dependency manifest и source archive consistency.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 4. Добавить отмену, повтор и fault injection; memory measurement на incremental/full режимах.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

## Trade-offs
Prefer measured, reversible improvements to speculative rewrites. Keep PostgreSQL 15 and current async Python stack; do not assume availability of unlisted extensions. Separate canonical data from derivative data and preserve query-time-only cross-repo resolution.

## Failure and rollback
A failure must not change current publication. New DB structures require new forward migration; no editing of already applied migrations. Benchmark memory/latency/locks where the feature is performance related.

## Implementation impact
src/code_crawler/incremental.py; src/code_crawler/source_adapters.py; src/code_crawler/ingestion.py; tests/integration/test_incremental_indexing.py

## Dependencies
B02,B03,B04
