# Design: OpenAPI to Spring handlers and Feign clients

## Current state
API contracts cannot yet link to local Java implementations or outgoing REST clients.

## Decisions
### D1. Parse effective Spring MVC/WebFlux mappings from class/method annotations including HTTP method, routes, consumes and produces.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D2. Derive route candidate keys without losing original path parameter names; include known base/server context.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D3. Resolve API operation to Java handler only when route, HTTP method and framework constraints match uniquely.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D4. Represent ambiguous controllers as candidates and unresolved or client calls as ExternalReference.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D5. Map DTO argument/response types only from signatures and explicit annotations; connect to existing Java Call Graph and SQL.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

## Storage and publication
Adapter produces local UCM facts; only central ingestion writes public.ucm_* tables. New typed tables need forward migrations. BUILDING snapshot can be partially parsed with diagnostics, but must pass final completeness and schema validation before publication.

## Security
Treat inputs as untrusted, bound parser size/depth, reject path traversal and prevent XML/URI external fetch. Never execute detected SQL or scripts. Unknown semantics remain UNKNOWN/PARTIAL and cannot be silently elevated.

## Source impact
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Implemented decisions

The immutable `java.http.routes` catalog uses the existing canonical Java AST and
symbols. Shared declaration/import lookup is extracted from D02 without adding a
parser. Java exposes HTTP facts in every profile; D07's Kafka wrapper forwards
both BPMN and HTTP catalogs and retains its own descriptor version prefix.

OpenAPI bindings consume D05 facts, local refs and captured application YAML only.
Whole-segment path variables normalize only for candidate lookup; originals and
two-source evidence remain. Unknown mappings/configuration/media constraints
produce PARTIAL or unresolved results, duplicate handlers remain AMBIGUOUS.
Feign selectors remain deferred. DTO associations require actual signatures and
explicit body semantics, never schema/class name matching.

Migration 0029 extends the existing relation registry with seven typed kinds;
no new storage or parser dependencies are introduced. Incremental versions cover
Java catalog, schemas and application configuration, including malformed config.
Cross-file dependencies preserve immutable snapshot reuse and repository scope.

Repeated publication exposed a PostgreSQL custom-plan underestimate in discovery
projection for fresh snapshot UUIDs. Only that query uses a generic plan inside a
savepoint, restoring the caller setting. PG integration verifies restoration and
repeated publish; measured projection execution was 4.197 ms with the generic plan
versus a custom-plan timeout over three seconds on the same captured workload.
