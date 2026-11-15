# Design: OpenAPI 3.x contract adapter

## Current state
REST contracts, endpoints, request/response schemas and references are not indexed.

## Decisions
### D1. Discover YAML/JSON by root openapi field; support dialect-aware OpenAPI 3.0, 3.1 and 3.2.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D2. Extract operations, params, body, responses, schemas, fields, media types, security, callbacks and webhooks.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D3. Support composition, discriminator, required/nullable and recursive local references without unbounded expansion.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D4. Support OpenAPI 3.2 QUERY, additionalOperations and querystring; preserve unsupported vendor extensions with diagnostics.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D5. Resolve local and repository-relative refs; keep remote URI references deferred with no network access.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

## Storage and publication
Adapter produces local UCM facts; only central ingestion writes public.ucm_* tables. New typed tables need forward migrations. BUILDING snapshot can be partially parsed with diagnostics, but must pass final completeness and schema validation before publication.

## Security
Treat inputs as untrusted, bound parser size/depth, reject path traversal and prevent XML/URI external fetch. Never execute detected SQL or scripts. Unknown semantics remain UNKNOWN/PARTIAL and cannot be silently elevated.

## Source impact
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Resolved implementation contract

The adapter extends existing Symbol/Value/Relation storage rather than introducing
parallel entities or arbitrary JSON payloads. Migration 0025 adds OPENAPI_* symbol
kinds and OPENAPI_ATTRIBUTE/OPENAPI_REF endpoint registrations. Every syntax node
is addressed by repository/path/JSON Pointer; typed scalar Values and CONTAINS
retain the source tree. Operation method/path and document dialect have explicit
attributes. Evidence ranges use captured UTF-8 byte columns and archive retrieval.

Safe PyYAML syntax nodes provide YAML/JSON coordinates without constructing custom
objects. An event preflight enforces 4 MiB, depth 64 and 20,000 scalar/collection
budgets; aliases/custom tags/duplicates/multi-document input are rejected. JSON
gets an additional strict duplicate/non-finite check. This adds an explicit PyYAML
dependency through uv (already present transitively); no ad-hoc YAML parser is used.

Root openapi activates 3.0.x/3.1.x/3.2.x documents. Captured relative-reference
closure activates schema fragments, never reads the filesystem or network, and
records positive/negative file dependencies. Reachable file/dialect membership
is included in prepared analysis identity so newly referenced unchanged fragments
are reanalyzed. Refs form finite graph edges; remote/base-scope refs remain deferred
SymbolSelectors. Missing and ambiguous targets preserve explicit Resolution and
UNKNOWN certainty. Literal examples/vendor data do not cause reference resolution.

The JSON route has one owner: OpenAPI in the CLI. TypeScript's standalone default
remains compatible through include_json=True; CLI sets False. Both JS/TS adapters
receive captured tsconfig.json through prepare_inventory independent of route
language, with the existing dependency mechanism and an analyzer version bump.
The integration fixture verifies alias resolution and config invalidation.

Dialect-sensitive keywords are preserved, not translated into an effective
validation schema: nullable in 3.0, JSON Schema null unions/boolean schemas in
3.1+, QUERY/additionalOperations/querystring in 3.2. Incompatible keywords have
DIALECT diagnostics; unsupported vendor/dynamic scope semantics remain PARTIAL.
Discriminator explicit mappings resolve local targets; implicit runtime matching
and Java/HTTP bindings are deferred. Full supported behavior and limitations:
docs/openapi-contracts.md.
