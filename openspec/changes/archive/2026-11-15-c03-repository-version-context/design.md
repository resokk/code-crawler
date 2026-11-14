# Design: Выбор согласованного контекста версий репозиториев

## Context
При cross-repo поиске нельзя подбирать произвольные latest versions без deployment/pinned constraints; текущие запросы scoped to one published snapshot.

## Proposed design
### Decision 1
Реализовать resolver_contexts с режимами LATEST_INDEXED, PINNED_SNAPSHOTS, DEPLOYMENT_CONTEXT и immutable selection manifest.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 2
Для pinned проверять repo ownership, readiness и наличие retained snapshot; для deployment явное mapping service/deploy to snapshot.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 3
Разделить выбор версии, разрешение candidate и publication; missing versions и unknown deployments — явная ошибка/неопределённость.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 4
Включать context fingerprint в кэш и Evidence path; поддержать pin retention при GC.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

## Consistency and lifecycle
- Canonical UCM snapshots are immutable. Derived search documents, catalogs, embeddings and resolver caches carry snapshot/generation keys.
- Indexing one repository MUST NOT depend on another; remote references are resolved only at query-time.
- Published readers MUST see one coherent generation across one query or report explicit partial availability.
- No unauthorised access to repository source/evidence; default fail closed when auth is needed.

## Risks and recovery
Avoid unbounded search/fanout, wrong version selection and leakage of secrets via embeddings. A failed derivative generation leaves the previous published generation available. Forward migrations and PG15 tests are required for schema changes.

## Interfaces affected
src/code_crawler/migrations/; src/code_crawler/snapshots.py; src/code_crawler/search.py; docs/; tests/integration/

## Dependencies
C02 может разрабатываться параллельно
