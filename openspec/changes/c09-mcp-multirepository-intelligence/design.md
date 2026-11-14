# Design: MCP-инструменты межрепозиторного Code Intelligence

## Context
FastMCP сейчас предоставляет только repo-scoped tools; нет контекстного глобального search, trace и impact analysis.

## Proposed design
### Decision 1
Добавить MCP tools search_global, resolve_external_reference, trace_cross_repository, impact_analysis с версионированным context.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 2
В каждом запросе проверять principal ACL, max depth/limit/fanout/time, input selectors и cancellation.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 3
Стандартизировать вывод candidates, resolution, evidence path, source snapshot, coverage, truncation, explainability.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 4
Сделать error handling без утечки недоступных репозиториев; docs с реальными примерами запросов.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

## Consistency and lifecycle
- Canonical UCM snapshots are immutable. Derived search documents, catalogs, embeddings and resolver caches carry snapshot/generation keys.
- Indexing one repository MUST NOT depend on another; remote references are resolved only at query-time.
- Published readers MUST see one coherent generation across one query or report explicit partial availability.
- No unauthorised access to repository source/evidence; default fail closed when auth is needed.

## Risks and recovery
Avoid unbounded search/fanout, wrong version selection and leakage of secrets via embeddings. A failed derivative generation leaves the previous published generation available. Forward migrations and PG15 tests are required for schema changes.

## Interfaces affected
src/code_crawler/server.py; src/code_crawler/search.py; tests/test_server.py; docs/server.md

## Dependencies
A02,C03,C04,C06,C08
