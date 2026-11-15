# Design: Kotlin UCM symbols, calls and Java interoperability

## Baseline
Kotlin source extraction is not wired to canonical SourceAdapter registry.

## Architecture
### Decision 1
Discover Kotlin .kt/.kts with explicit support and diagnostics for Kotlin scripts.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 2
Extract packages, imports, classes, interfaces, objects, functions, constructors, properties, scopes and occurrences.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 3
Handle overloads, extension functions, receivers, nullable types and generic signatures without false resolution.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 4
Resolve local Kotlin calls and supported Java interoperability via shared UCM symbols, preserving unknown targets.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 5
Integrate SQL construction/execution support for explicit supported Kotlin JDBC/Spring patterns and incremental invalidation.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

## SourceAdapter lifecycle
Detect file → safe parse → AST/language-specific facts → local reference resolution → UCM Batch → centralized PostgreSQL staging/validation/publication. Record file ownership and negative/positive dependencies for incremental reanalysis.

## Security and failure policy
No network lookups by default, no execution, no trust in input code or metadata. Constrain parser complexity and return diagnostics on malformed input. Failed analysis must not replace a currently published snapshot.

## Compatibility and tests
Add new UCM EntityType/RelationKind only if necessary, using forward migrations. Preserve existing Java/SQL/BPMN facts and compare full vs incremental output on same fixture.
