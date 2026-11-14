# Design: Сокращение времени транзакции при индексации

## Background
index_incremental начинает транзакцию до CPU анализа каждого _SLICE, затем держит её на staging, cloning и архивировании.

## Architecture decisions
### 1. Разделить immutable source capture/CPU analysis и стадии транзакционной записи; выбрать spool/staging с ограниченной памятью.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 2. Обеспечить snapshot input fingerprint и повторную verify перед фиксацией staged данных.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 3. Переиспользованные facts клонировать из того же immutable baseline при CAS publication, без long-running repo lock.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 4. Обеспечить idempotent cleanup after crash и работу concurrent indexing jobs.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

## Trade-offs
Prefer measured, reversible improvements to speculative rewrites. Keep PostgreSQL 15 and current async Python stack; do not assume availability of unlisted extensions. Separate canonical data from derivative data and preserve query-time-only cross-repo resolution.

## Failure and rollback
A failure must not change current publication. New DB structures require new forward migration; no editing of already applied migrations. Benchmark memory/latency/locks where the feature is performance related.

## Implementation impact
src/code_crawler/incremental.py; src/code_crawler/ingestion.py; src/code_crawler/snapshots.py; tests/integration/test_incremental_indexing.py

## Dependencies
B01; учитывать B02/B05
