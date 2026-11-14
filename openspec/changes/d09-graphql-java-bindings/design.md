# Design: GraphQL Java resolver and DataFetcher bindings

## Baseline
No connection from GraphQL root/nested field to Spring GraphQL methods, BatchMapping or DataFetcher registration.

## Architecture
### Decision 1
Support Spring GraphQL QueryMapping, MutationMapping, SubscriptionMapping, SchemaMapping and BatchMapping.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 2
Resolve typed field identity including owner type, field name, argument types and return types.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 3
Detect supported GraphQL Java DataFetcher registration and DGS profiles, with version-specific capabilities.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 4
Treat default property/data fetching as possible but not a fictitious handler; ambiguous resolvers remain uncertain.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 5
Link field→local Java symbol→existing CALLS→SQL without reparsing SQL; preserve deferred external target references.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

## SourceAdapter lifecycle
Detect file → safe parse → AST/language-specific facts → local reference resolution → UCM Batch → centralized PostgreSQL staging/validation/publication. Record file ownership and negative/positive dependencies for incremental reanalysis.

## Security and failure policy
No network lookups by default, no execution, no trust in input code or metadata. Constrain parser complexity and return diagnostics on malformed input. Failed analysis must not replace a currently published snapshot.

## Compatibility and tests
Add new UCM EntityType/RelationKind only if necessary, using forward migrations. Preserve existing Java/SQL/BPMN facts and compare full vs incremental output on same fixture.
