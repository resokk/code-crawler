# Proposal: GraphQL Java resolver and DataFetcher bindings

## Why
No connection from GraphQL root/nested field to Spring GraphQL methods, BatchMapping or DataFetcher registration.

## Goal
Implement GraphQL Java resolver and DataFetcher bindings as a dedicated, versioned SourceAdapter producing canonical UCM facts.

## Scope
- Support Spring GraphQL QueryMapping, MutationMapping, SubscriptionMapping, SchemaMapping and BatchMapping.
- Resolve typed field identity including owner type, field name, argument types and return types.
- Detect supported GraphQL Java DataFetcher registration and DGS profiles, with version-specific capabilities.
- Treat default property/data fetching as possible but not a fictitious handler; ambiguous resolvers remain uncertain.
- Link field→local Java symbol→existing CALLS→SQL without reparsing SQL; preserve deferred external target references.

## Non-goals
- No runtime execution of source, SQL, network calls or remote services.
- No global cross-repository linking during ingestion.
- Do not create a second storage graph or directly persist from adapters.

## Dependencies
Existing UCM Core, SourceAdapter registry, Evidence and incremental manifests. For resolver bindings, prerequisite schema/parsing capability.

## Priority
P1/P2. Build in parallel with discovery work after stable R1 core.
