# Design: BPMN Java handler bindings

## Current state
No links between BPMN tasks, Java delegates and external workers.

## Decisions
### D1. Implement version-aware Camunda and Flowable binding profiles.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D2. Resolve JavaDelegate, delegateExpression, Spring bean, external worker/topic to local Java symbols.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D3. Track process variable mapping as typed facts with uncertain data lineage made explicit.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D4. Create evidence-backed BPMN task to Java handler relations; ambiguous beans remain ambiguous.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D5. Produce ExternalReference selectors for external workers/processes without global lookup.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

## Storage and publication
Adapter produces local UCM facts; only central ingestion writes public.ucm_* tables. New typed tables need forward migrations. BUILDING snapshot can be partially parsed with diagnostics, but must pass final completeness and schema validation before publication.

## Security
Treat inputs as untrusted, bound parser size/depth, reject path traversal and prevent XML/URI external fetch. Never execute detected SQL or scripts. Unknown semantics remain UNKNOWN/PARTIAL and cannot be silently elevated.

## Source impact
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Implemented decisions

The registry has a two-phase local preparation lifecycle: optional frozen typed
catalog exports, then consumers bind against a read-only mapping. Consumer
`catalog_keys` avoids exports when no catalog is requested; safe XML root-only
preflight avoids retaining a Java AST catalog in projects without BPMN. Source identity,
producer ownership, byte ranges, deep immutability and version stability are
validated in a worker thread. No mutable AST, DB connection or filesystem root is
passed to the consumer. Other adapters keep the existing prepare/analyze contract.

Java exports `JavaBindingCatalog` from the current canonical extractor results,
including compatible contract/signature, bean/worker registrations, variable
accesses and parser exclusions. Symbols profile caches that extraction for its
own facts; richer profiles reuse their existing analyzer AST. No duplicate Java
or SQL parser/analyzer is added. The catalog hash includes profile and captured
file hashes, so added/removed/renamed candidates invalidate the BPMN scope even
when XML bytes are unchanged.

BPMN adapter `bpmn/2` preserves schema analyzer `bpmn/1` and adds PARTIAL
`bpmn.java/1`. Profiles are auto, camunda7, camunda8, flowable6, flowable7; explicit
profile is stored in CLI jobs and fingerprints. Unknown runtime deployment and
Spring conditional registration remain unproven. One compatible declared method
gets RESOLVED/INFERRED; different methods get AMBIGUOUS; conflicting registrations,
selectors or parser exclusions get PARTIAL instead of a false unique target.

Migration 0024 adds six normative relation kinds over existing Symbol/Value
storage: BPMN_HANDLER, BPMN_INPUT_MAPPING, BPMN_OUTPUT_MAPPING,
BPMN_READS_VARIABLE, BPMN_WRITES_VARIABLE, BPMN_VARIABLE_BINDING. Handler Evidence
contains both BPMN and Java ranges. Mapping-to-variable links are only name-match
candidates with PARTIAL/AMBIGUOUS Resolution and INFERRED Certainty. Dynamic names
are UNKNOWN. XML configuration mapping presence may be STATIC_PROVEN, not runtime
lineage. Contextual variable facts belong to the BPMN file and retain Java ranges
in Evidence, keeping incremental ownership unambiguous.

Deferred role-prefixed SymbolSelectors are retained for missing/unsupported
handlers and external workers/processes. No other repository is queried. Existing
published reader/trace composes BPMN_HANDLER with Java EXECUTES_SQL; ambiguous
handler candidates are not followed as a resolved target.

See `docs/bpmn-java-bindings.md` for supported APIs, limits and failure behavior.
