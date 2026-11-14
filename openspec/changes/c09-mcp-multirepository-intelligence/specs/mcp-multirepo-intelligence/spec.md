# Capability: mcp-multirepo-intelligence

## ADDED Requirements

### Requirement: Global candidate search
The system MUST implement: Добавить MCP tools search_global, resolve_external_reference, trace_cross_repository, impact_analysis с версионированным context.

#### Scenario: Global candidate search
- GIVEN два репозитория содержат подходящие Symbol
- WHEN MCP global search вызывают
- THEN возвращаются оба с repo+snapshot identities.

### Requirement: Impact analysis
The system MUST implement: В каждом запросе проверять principal ACL, max depth/limit/fanout/time, input selectors и cancellation.

#### Scenario: Impact analysis
- GIVEN публичный метод A вызывает B через external ref
- WHEN анализируют impact B
- THEN возвращён bounded обратный путь с Evidence.

### Requirement: ACL enforcement
The system MUST implement: Стандартизировать вывод candidates, resolution, evidence path, source snapshot, coverage, truncation, explainability.

#### Scenario: ACL enforcement
- GIVEN principal имеет доступ только к A
- WHEN global search вызывают
- THEN B не раскрывается.

### Requirement: Limits
The system MUST implement: Сделать error handling без утечки недоступных репозиториев; docs с реальными примерами запросов.

#### Scenario: Limits
- GIVEN user задаёт depth=100
- WHEN tool вызывают
- THEN запрос отклоняется до БД.

### Requirement: Explicit provenance and uncertainty
Every derived search result MUST preserve source snapshot, originating UCM entity and distinguish RESOLVED, AMBIGUOUS and UNRESOLVED; similarity alone MUST NOT establish a definite code dependency.

#### Scenario: Insufficient evidence
- GIVEN a candidate matches only by name or semantic similarity
- WHEN retrieval returns it
- THEN it is a candidate, not a proven cross-repository relationship
