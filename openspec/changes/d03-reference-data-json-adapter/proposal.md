# Proposal: Reference dataset JSON adapter

## Why
Reference datasets of type-data.json are absent; dataset type must not be assumed to equal DB table.

## Goal
Extend current UCM, not create a parallel graph. Detect configurable type-data.json file patterns and validate JSON structure/version. Extract ReferenceDataset, Field, Record, keys, value types and exact JSON pointers. Distinguish source presence from runtime load/deployment status. Apply bounded record handling and partial diagnostics for malformed entries. Never infer SQL table from the type prefix; preserve identity in repository snapshot.

## Scope
- Detect configurable type-data.json file patterns and validate JSON structure/version.
- Extract ReferenceDataset, Field, Record, keys, value types and exact JSON pointers.
- Distinguish source presence from runtime load/deployment status.
- Apply bounded record handling and partial diagnostics for malformed entries.
- Never infer SQL table from the type prefix; preserve identity in repository snapshot.

## Non-goals
- No source execution, remote network lookup, or direct database writes from adapter.
- No mandatory global cross-repository graph resolution during local ingest.

## Integration
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Dependencies
Existing UCM Core and SourceAdapter registry; for bindings, corresponding schema adapter and Java analysis.
