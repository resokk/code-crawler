# Proposal: Reference data loader and DB mappings

## Why
No path from dataset fields through loader to SQL or ORM column.

## Goal
Extend current UCM, not create a parallel graph. Find supported Java/Groovy/PLPlus loader patterns and their dataset identity. Extract DataLoadOperation and DataLoadMapping with field paths, transformations and DB-context provenance. Link to existing SQL_EXECUTE, ORM and DATA_ACCESS facts instead of building a duplicate SQL graph. For reflection/dynamic mapping return PARTIAL/UNKNOWN and evidence, not guessed targets. For external loader references emit deferred lookup keys.

## Scope
- Find supported Java/Groovy/PLPlus loader patterns and their dataset identity.
- Extract DataLoadOperation and DataLoadMapping with field paths, transformations and DB-context provenance.
- Link to existing SQL_EXECUTE, ORM and DATA_ACCESS facts instead of building a duplicate SQL graph.
- For reflection/dynamic mapping return PARTIAL/UNKNOWN and evidence, not guessed targets.
- For external loader references emit deferred lookup keys.

## Non-goals
- No source execution, remote network lookup, or direct database writes from adapter.
- No mandatory global cross-repository graph resolution during local ingest.

## Integration
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Dependencies
Existing UCM Core and SourceAdapter registry; for bindings, corresponding schema adapter and Java analysis.
