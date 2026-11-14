# Proposal: BPMN 2.0 XML to UCM

## Why
BPMN process definitions and control flow are not indexed.

## Goal
Extend current UCM, not create a parallel graph. Discover BPMN XML and safely parse namespaces without DTD, XXE or network access. Extract process, start/end events, service/user tasks, subprocesses, gateways, sequence flows and conditions. Preserve process variables, expressions, input/output mappings, extension elements and engine hints. Represent graph edges as typed UCM relations with SourceRange/Evidence, not opaque JSON. Resolve local element IDs; create deferred ExternalReference for external worker/process IDs.

## Scope
- Discover BPMN XML and safely parse namespaces without DTD, XXE or network access.
- Extract process, start/end events, service/user tasks, subprocesses, gateways, sequence flows and conditions.
- Preserve process variables, expressions, input/output mappings, extension elements and engine hints.
- Represent graph edges as typed UCM relations with SourceRange/Evidence, not opaque JSON.
- Resolve local element IDs; create deferred ExternalReference for external worker/process IDs.

## Non-goals
- No source execution, remote network lookup, or direct database writes from adapter.
- No mandatory global cross-repository graph resolution during local ingest.

## Integration
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Dependencies
Existing UCM Core and SourceAdapter registry; for bindings, corresponding schema adapter and Java analysis.
