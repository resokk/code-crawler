# Proposal: GraphQL SDL and introspection schema adapter

## Why
No GraphQL schema AST, fields, operations, directives or schema-level external references in UCM.

## Goal
Implement GraphQL SDL and introspection schema adapter as a dedicated, versioned SourceAdapter producing canonical UCM facts.

## Scope
- Discover .graphql/.graphqls/.gql SDL and supported introspection JSON sources.
- Parse local schema definitions and type/schema extensions into consistent composed schema, with source provenance.
- Model SCALAR, OBJECT, INPUT_OBJECT, ENUM, INTERFACE, UNION, field arguments and exact list/non-null modifiers.
- Extract actual Query/Mutation/Subscription root type fields, custom root names, directives and deprecations.
- Preserve unknown federation extensions and unresolved schema components without runtime GraphQL execution.

## Non-goals
- No runtime execution of source, SQL, network calls or remote services.
- No global cross-repository linking during ingestion.
- Do not create a second storage graph or directly persist from adapters.

## Dependencies
Existing UCM Core, SourceAdapter registry, Evidence and incremental manifests. For resolver bindings, prerequisite schema/parsing capability.

## Priority
P1/P2. Build in parallel with discovery work after stable R1 core.
