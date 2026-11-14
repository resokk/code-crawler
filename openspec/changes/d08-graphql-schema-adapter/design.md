# Design: GraphQL SDL and introspection schema adapter

## Baseline
No GraphQL schema AST, fields, operations, directives or schema-level external references in UCM.

## Architecture
### Decision 1
Discover .graphql/.graphqls/.gql SDL and supported introspection JSON sources.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 2
Parse local schema definitions and type/schema extensions into consistent composed schema, with source provenance.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 3
Model SCALAR, OBJECT, INPUT_OBJECT, ENUM, INTERFACE, UNION, field arguments and exact list/non-null modifiers.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 4
Extract actual Query/Mutation/Subscription root type fields, custom root names, directives and deprecations.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 5
Preserve unknown federation extensions and unresolved schema components without runtime GraphQL execution.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

## SourceAdapter lifecycle
Detect file → safe parse → AST/language-specific facts → local reference resolution → UCM Batch → centralized PostgreSQL staging/validation/publication. Record file ownership and negative/positive dependencies for incremental reanalysis.

## Security and failure policy
No network lookups by default, no execution, no trust in input code or metadata. Constrain parser complexity and return diagnostics on malformed input. Failed analysis must not replace a currently published snapshot.

## Compatibility and tests
Add new UCM EntityType/RelationKind only if necessary, using forward migrations. Preserve existing Java/SQL/BPMN facts and compare full vs incremental output on same fixture.
