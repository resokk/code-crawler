# Design: Инкрементальность на реальных Java/Groovy/PLPlus репозиториях

## Background
Per-adapter invalidation реализована, но OpenSpec содержит открытый пункт про реальный mixed-language репозиторий.

## Architecture decisions
### 1. Подготовить версионированный test fixture, представляющий package imports, CFT selectors и Groovy dependencies.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 2. Фиксировать список adapter invocations и reuse manifests при изменении Java source/catalog.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 3. Проверить транзитивную invalidation связанных языков и отсутствие сброса unrelated facts.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 4. Проверить rename/delete, отсутствующие dependencies и untracked files.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

## Trade-offs
Prefer measured, reversible improvements to speculative rewrites. Keep PostgreSQL 15 and current async Python stack; do not assume availability of unlisted extensions. Separate canonical data from derivative data and preserve query-time-only cross-repo resolution.

## Failure and rollback
A failure must not change current publication. New DB structures require new forward migration; no editing of already applied migrations. Benchmark memory/latency/locks where the feature is performance related.

## Implementation impact
src/code_crawler/source_adapters.py; src/code_crawler/incremental.py; tests/integration/test_source_adapter_registry.py; docs/source-adapters.md

## Dependencies
B05 желательно
