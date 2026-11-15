# Proposal: VBScript symbols, calls and embedded SQL

## Why
VBScript is in target language coverage but no canonical extractor exists.

## Goal
Implement VBScript symbols, calls and embedded SQL as a dedicated, versioned SourceAdapter producing canonical UCM facts.

## Scope
- Integrate ANTLR VBScript grammar and parser diagnostics with SourceAdapter registry.
- Extract sub/function declarations, parameters, class/method/property statements, scopes and explicit calls.
- Detect static ADODB and SQL literal/build patterns without equating strings with execution.
- Distinguish late-bound COM object methods and dynamic Eval/CreateObject calls as partial external references.
- Preserve case-insensitive identifier semantics and byte-accurate source positions.

## Non-goals
- No runtime execution of source, SQL, network calls or remote services.
- No global cross-repository linking during ingestion.
- Do not create a second storage graph or directly persist from adapters.

## Dependencies
Existing UCM Core, SourceAdapter registry, Evidence and incremental manifests. For resolver bindings, prerequisite schema/parsing capability.

## Priority
P1/P2. Build in parallel with discovery work after stable R1 core.
