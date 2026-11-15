# Proposal: BPMN Java handler bindings

## Why
No links between BPMN tasks, Java delegates and external workers.

## Goal
Extend current UCM, not create a parallel graph. Implement version-aware Camunda and Flowable binding profiles. Resolve JavaDelegate, delegateExpression, Spring bean, external worker/topic to local Java symbols. Track process variable mapping as typed facts with uncertain data lineage made explicit. Create evidence-backed BPMN task to Java handler relations; ambiguous beans remain ambiguous. Produce ExternalReference selectors for external workers/processes without global lookup.

## Scope
- Implement version-aware Camunda and Flowable binding profiles.
- Resolve JavaDelegate, delegateExpression, Spring bean, external worker/topic to local Java symbols.
- Track process variable mapping as typed facts with uncertain data lineage made explicit.
- Create evidence-backed BPMN task to Java handler relations; ambiguous beans remain ambiguous.
- Produce ExternalReference selectors for external workers/processes without global lookup.

## Non-goals
- No source execution, remote network lookup, or direct database writes from adapter.
- No mandatory global cross-repository graph resolution during local ingest.

## Integration
src/code_crawler/source_adapters.py; src/code_crawler/ucm.py; src/code_crawler/migrations/; src/code_crawler/java_adapter.py (when applicable); tests/; docs/

## Dependencies
Existing UCM Core and SourceAdapter registry; for bindings, corresponding schema adapter and Java analysis.
