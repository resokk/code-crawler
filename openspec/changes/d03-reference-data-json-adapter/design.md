# Design: Reference dataset JSON adapter

## Current state
Reference datasets of type-data.json are absent; dataset type must not be assumed to equal DB table.

## Decisions
### D1. Detect configurable type-data.json file patterns and validate JSON structure/version.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D2. Extract ReferenceDataset, Field, Record, keys, value types and exact JSON pointers.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D3. Distinguish source presence from runtime load/deployment status.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D4. Apply bounded record handling and partial diagnostics for malformed entries.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D5. Never infer SQL table from the type prefix; preserve identity in repository snapshot.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

## Storage and publication
Adapter produces local UCM facts; only central ingestion writes public.ucm_* tables. New typed tables need forward migrations. BUILDING snapshot can be partially parsed with diagnostics, but must pass final completeness and schema validation before publication.

## Security
Treat inputs as untrusted, bound parser size/depth, reject path traversal and prevent XML/URI external fetch. Never execute detected SQL or scripts. Unknown semantics remain UNKNOWN/PARTIAL and cannot be silently elevated.

## Source impact
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/
