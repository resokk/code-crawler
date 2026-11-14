# Design: Reference data loader and DB mappings

## Current state
No path from dataset fields through loader to SQL or ORM column.

## Decisions
### D1. Find supported Java/Groovy/PLPlus loader patterns and their dataset identity.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D2. Extract DataLoadOperation and DataLoadMapping with field paths, transformations and DB-context provenance.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D3. Link to existing SQL_EXECUTE, ORM and DATA_ACCESS facts instead of building a duplicate SQL graph.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D4. For reflection/dynamic mapping return PARTIAL/UNKNOWN and evidence, not guessed targets.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

### D5. For external loader references emit deferred lookup keys.
Implement within SourceAdapter lifecycle: discovery, safe parser, typed facts, local resolution, normalized UCM entities/relations/evidence and diagnostics. Stable logical IDs are scoped to repository and source path; preserve incremental dependencies and versioned coverage.

## Storage and publication
Adapter produces local UCM facts; only central ingestion writes public.ucm_* tables. New typed tables need forward migrations. BUILDING snapshot can be partially parsed with diagnostics, but must pass final completeness and schema validation before publication.

## Security
Treat inputs as untrusted, bound parser size/depth, reject path traversal and prevent XML/URI external fetch. Never execute detected SQL or scripts. Unknown semantics remain UNKNOWN/PARTIAL and cannot be silently elevated.

## Source impact
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/
