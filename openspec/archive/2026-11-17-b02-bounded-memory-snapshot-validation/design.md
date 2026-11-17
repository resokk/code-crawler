# Design: Порционная проверка целостности snapshot

## Background
publication.load_snapshot_batch читает все таблицы и восстанавливает полный UcmBatch при validate_snapshot; память растёт с числом фактов.

## Architecture decisions
### 1. Сформировать полный реестр UcmBatch semantic invariants с отображением на проверки SQL/stream.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 2. Проверять unique identities, entity types, typed FK, evidence ranges, relation endpoints, scopes, SQL construction/bindings и ORM инварианты порциями.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 3. Сохранять validation receipt и READY только по завершении всех проверок в контролируемом транзакционном протоколе.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 4. Сопоставить решения старого и нового валидатора на корректных и искусственно повреждённых snapshots; убрать обязательную полную model hydration из readiness.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

## Trade-offs
Prefer measured, reversible improvements to speculative rewrites. Keep PostgreSQL 15 and current async Python stack; do not assume availability of unlisted extensions. Separate canonical data from derivative data and preserve query-time-only cross-repo resolution.

## Failure and rollback
A failure must not change current publication. New DB structures require new forward migration; no editing of already applied migrations. Benchmark memory/latency/locks where the feature is performance related.

## Implementation impact
src/code_crawler/publication.py; src/code_crawler/ingestion.py; src/code_crawler/ucm.py; tests/integration/test_publication.py; docs/ucm-publication.md

## Dependencies
B01; разделить на inventory, references и readiness
