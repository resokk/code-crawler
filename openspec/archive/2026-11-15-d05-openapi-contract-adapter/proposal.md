# Proposal: OpenAPI 3.x contract adapter

## Why
REST contracts, endpoints, request/response schemas and references are not indexed.

## Goal
Extend current UCM, not create a parallel graph. Discover YAML/JSON by root openapi field; support dialect-aware OpenAPI 3.0, 3.1 and 3.2. Extract operations, params, body, responses, schemas, fields, media types, security, callbacks and webhooks. Support composition, discriminator, required/nullable and recursive local references without unbounded expansion. Support OpenAPI 3.2 QUERY, additionalOperations and querystring; preserve unsupported vendor extensions with diagnostics. Resolve local and repository-relative refs; keep remote URI references deferred with no network access.

## Scope
- Discover YAML/JSON by root openapi field; support dialect-aware OpenAPI 3.0, 3.1 and 3.2.
- Extract operations, params, body, responses, schemas, fields, media types, security, callbacks and webhooks.
- Support composition, discriminator, required/nullable and recursive local references without unbounded expansion.
- Support OpenAPI 3.2 QUERY, additionalOperations and querystring; preserve unsupported vendor extensions with diagnostics.
- Resolve local and repository-relative refs; keep remote URI references deferred with no network access.

## Non-goals
- No source execution, remote network lookup, or direct database writes from adapter.
- No mandatory global cross-repository graph resolution during local ingest.

## Integration
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Dependencies
Existing UCM Core and SourceAdapter registry; for bindings, corresponding schema adapter and Java analysis.
