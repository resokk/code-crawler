# Proposal: MCP-инструменты межрепозиторного Code Intelligence

## Why
FastMCP сейчас предоставляет только repo-scoped tools; нет контекстного глобального search, trace и impact analysis.

## Outcome
MCP-инструменты межрепозиторного Code Intelligence. Добавить MCP tools search_global, resolve_external_reference, trace_cross_repository, impact_analysis с версионированным context. В каждом запросе проверять principal ACL, max depth/limit/fanout/time, input selectors и cancellation. Стандартизировать вывод candidates, resolution, evidence path, source snapshot, coverage, truncation, explainability. Сделать error handling без утечки недоступных репозиториев; docs с реальными примерами запросов.

## Scope
- Добавить MCP tools search_global, resolve_external_reference, trace_cross_repository, impact_analysis с версионированным context.
- В каждом запросе проверять principal ACL, max depth/limit/fanout/time, input selectors и cancellation.
- Стандартизировать вывод candidates, resolution, evidence path, source snapshot, coverage, truncation, explainability.
- Сделать error handling без утечки недоступных репозиториев; docs с реальными примерами запросов.

## Non-goals
Сервер остаётся read-only/stateless; не индексирует и не запускает код.

## Dependencies
A02,C03,C04,C06,C08

## Impacted code
src/code_crawler/server.py; src/code_crawler/search.py; tests/test_server.py; docs/server.md

## Priority
P1
