# Design: Ускорение загрузки через FK и индексы

## Background
При нагрузке ~930 тыс. entities прежний batch не завершился за 50 минут; причины включали FK проверки и текстовые составные ключи.

## Architecture decisions
### 1. Измерить COPY staging, INSERT SELECT и SET CONSTRAINTS IMMEDIATE отдельно на PG15.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 2. Изучить collations C/locale для entity IDs и эффект индексов; менять схему только новой forward migration.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 3. Оптимизировать перенесение в canonical таблицы, порядок FK, access patterns и ограничить temp space.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

### 4. Сравнить целостность и результаты до/после, rollback при нарушении FK и overhead добавленных индексов.
**Implementation:** isolate this decision behind existing UCM ingestion/publication contracts. Add deterministic fixtures, explicit error paths and performance instrumentation where relevant. Reject unsafe shortcuts that disable validation, lose Evidence or mix repository snapshots.

## Trade-offs
Prefer measured, reversible improvements to speculative rewrites. Keep PostgreSQL 15 and current async Python stack; do not assume availability of unlisted extensions. Separate canonical data from derivative data and preserve query-time-only cross-repo resolution.

## Failure and rollback
A failure must not change current publication. New DB structures require new forward migration; no editing of already applied migrations. Benchmark memory/latency/locks where the feature is performance related.

## Implementation impact
src/code_crawler/ingestion.py; src/code_crawler/migrations/; docs/query-indexes.md; tests/integration/test_bulk_ingestion.py

## Dependencies
B01; совместим с B03
