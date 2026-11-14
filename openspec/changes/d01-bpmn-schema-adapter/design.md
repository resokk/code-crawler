# Design: BPMN 2.0 XML to UCM

## Current state
BPMN process definitions and control flow are not indexed.

## Decisions
### D1. Discover BPMN XML and safely parse namespaces without DTD, XXE or network access.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D2. Extract process, start/end events, service/user tasks, subprocesses, gateways, sequence flows and conditions.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D3. Preserve process variables, expressions, input/output mappings, extension elements and engine hints.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D4. Represent graph edges as typed UCM relations with SourceRange/Evidence, not opaque JSON.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D5. Resolve local element IDs; create deferred ExternalReference for external worker/process IDs.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

## Storage and publication
Adapter produces local UCM facts; only central ingestion writes public.ucm_* tables. New typed tables need forward migrations. BUILDING snapshot can be partially parsed with diagnostics, but must pass final completeness and schema validation before publication.

## Security
Treat inputs as untrusted, bound parser size/depth, reject path traversal and prevent XML/URI external fetch. Never execute detected SQL or scripts. Unknown semantics remain UNKNOWN/PARTIAL and cannot be silently elevated.

## Source impact
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Implemented mapping

Reuse `Symbol` with a new `BPMN_ELEMENT` kind instead of a parallel entity graph.
Expanded XML QName identifies the element type. Existing `Value(LITERAL)` stores
attributes/text; `BPMN_ATTRIBUTE`, `BPMN_TEXT`, `CONTAINS` preserve their ownership.
Addressable sequence-flow symbols use `BPMN_FLOW_SOURCE`/`BPMN_FLOW_TARGET`;
local callActivity uses `BPMN_CALLS_PROCESS`. Migration 0020 extends the existing
symbol and relation registries, so central ingestion/read/publication remain shared.

Use stdlib Expat with DTD/entity rejection callbacks, UTF-8-only input and explicit
size/depth/element bounds. A rejected document emits diagnostics and no semantic
facts. Duplicate IDs are rejected instead of choosing a candidate. Bad flow
endpoints omit both endpoint links, preserving syntax with explicit diagnostics.
Known engine selectors use existing deferred SymbolSelector with role prefixes;
no target repository or Java binding is consulted. All coverage is explicitly
PARTIAL because runtime expressions/extensions are preserved without evaluation.
Detailed contract and limits: `docs/bpmn-schema.md`.
