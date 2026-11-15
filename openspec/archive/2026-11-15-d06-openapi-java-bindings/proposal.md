# Proposal: OpenAPI to Spring handlers and Feign clients

## Why
API contracts cannot yet link to local Java implementations or outgoing REST clients.

## Goal
Extend current UCM, not create a parallel graph. Parse effective Spring MVC/WebFlux mappings from class/method annotations including HTTP method, routes, consumes and produces. Derive route candidate keys without losing original path parameter names; include known base/server context. Resolve API operation to Java handler only when route, HTTP method and framework constraints match uniquely. Represent ambiguous controllers as candidates and unresolved or client calls as ExternalReference. Map DTO argument/response types only from signatures and explicit annotations; connect to existing Java Call Graph and SQL.

## Scope
- Parse effective Spring MVC/WebFlux mappings from class/method annotations including HTTP method, routes, consumes and produces.
- Derive route candidate keys without losing original path parameter names; include known base/server context.
- Resolve API operation to Java handler only when route, HTTP method and framework constraints match uniquely.
- Represent ambiguous controllers as candidates and unresolved or client calls as ExternalReference.
- Map DTO argument/response types only from signatures and explicit annotations; connect to existing Java Call Graph and SQL.

## Non-goals
- No source execution, remote network lookup, or direct database writes from adapter.
- No mandatory global cross-repository graph resolution during local ingest.

## Integration
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Dependencies
Existing UCM Core and SourceAdapter registry; for bindings, corresponding schema adapter and Java analysis.
