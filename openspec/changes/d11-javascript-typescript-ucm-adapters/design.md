# Design: JavaScript and TypeScript UCM adapters

## Baseline
No canonical JS/TS symbols/import graph or HTTP client extraction despite target language coverage.

## Architecture
### Decision 1
Use separate versioned adapters for .js/.jsx and .ts/.tsx, with file-routing and TS project config.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 2
Extract exports/imports, functions, classes, arrow functions, methods, variables, scopes, occurrences and type references.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 3
Resolve local module paths, reexports and deterministic same-repository calls; dynamic imports/calls preserve uncertainty.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 4
Capture supported fetch/axios HTTP client method/URL expressions as typed external API references.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 5
Preserve TS overloads, generics and interface declarations without claiming runtime implementation.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

## SourceAdapter lifecycle
Detect file → safe parse → AST/language-specific facts → local reference resolution → UCM Batch → centralized PostgreSQL staging/validation/publication. Record file ownership and negative/positive dependencies for incremental reanalysis.

## Security and failure policy
No network lookups by default, no execution, no trust in input code or metadata. Constrain parser complexity and return diagnostics on malformed input. Failed analysis must not replace a currently published snapshot.

## Compatibility and tests
Add new UCM EntityType/RelationKind only if necessary, using forward migrations. Preserve existing Java/SQL/BPMN facts and compare full vs incremental output on same fixture.
