# Proposal: JavaScript and TypeScript UCM adapters

## Why
No canonical JS/TS symbols/import graph or HTTP client extraction despite target language coverage.

## Goal
Implement JavaScript and TypeScript UCM adapters as a dedicated, versioned SourceAdapter producing canonical UCM facts.

## Scope
- Use separate versioned adapters for .js/.jsx and .ts/.tsx, with file-routing and TS project config.
- Extract exports/imports, functions, classes, arrow functions, methods, variables, scopes, occurrences and type references.
- Resolve local module paths, reexports and deterministic same-repository calls; dynamic imports/calls preserve uncertainty.
- Capture supported fetch/axios HTTP client method/URL expressions as typed external API references.
- Preserve TS overloads, generics and interface declarations without claiming runtime implementation.

## Non-goals
- No runtime execution of source, SQL, network calls or remote services.
- No global cross-repository linking during ingestion.
- Do not create a second storage graph or directly persist from adapters.

## Dependencies
Existing UCM Core, SourceAdapter registry, Evidence and incremental manifests. For resolver bindings, prerequisite schema/parsing capability.

## Priority
P1/P2. Build in parallel with discovery work after stable R1 core.
