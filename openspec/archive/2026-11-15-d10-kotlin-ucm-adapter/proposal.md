# Proposal: Kotlin UCM symbols, calls and Java interoperability

## Why
Kotlin source extraction is not wired to canonical SourceAdapter registry.

## Goal
Implement Kotlin UCM symbols, calls and Java interoperability as a dedicated, versioned SourceAdapter producing canonical UCM facts.

## Scope
- Discover Kotlin .kt/.kts with explicit support and diagnostics for Kotlin scripts.
- Extract packages, imports, classes, interfaces, objects, functions, constructors, properties, scopes and occurrences.
- Handle overloads, extension functions, receivers, nullable types and generic signatures without false resolution.
- Resolve local Kotlin calls and supported Java interoperability via shared UCM symbols, preserving unknown targets.
- Integrate SQL construction/execution support for explicit supported Kotlin JDBC/Spring patterns and incremental invalidation.

## Non-goals
- No runtime execution of source, SQL, network calls or remote services.
- No global cross-repository linking during ingestion.
- Do not create a second storage graph or directly persist from adapters.

## Dependencies
Existing UCM Core, SourceAdapter registry, Evidence and incremental manifests. For resolver bindings, prerequisite schema/parsing capability.

## Priority
P1/P2. Build in parallel with discovery work after stable R1 core.
