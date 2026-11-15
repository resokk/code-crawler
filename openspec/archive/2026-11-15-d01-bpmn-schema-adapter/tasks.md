# Tasks: BPMN 2.0 XML to UCM

Completed and verified on PostgreSQL 15; acceptance evidence is recorded below.

- [x] 1. Review existing SourceAdapter registry, UCM types, relation registry and schema migration patterns.
- [x] 2. Define typed entities, references and SourceAnalysis diagnostics for this format.
- [x] 3. Implement: Discover BPMN XML and safely parse namespaces without DTD, XXE or network access.
- [x] 4. Implement: Extract process, start/end events, service/user tasks, subprocesses, gateways, sequence flows and conditions.
- [x] 5. Implement: Preserve process variables, expressions, input/output mappings, extension elements and engine hints.
- [x] 6. Implement: Represent graph edges as typed UCM relations with SourceRange/Evidence, not opaque JSON.
- [x] 7. Implement: Resolve local element IDs; create deferred ExternalReference for external worker/process IDs.
- [x] 8. Write positive and negative conformance test: BPMN with gateway and two flows / indexing / both transitions and guards remain addressable
- [x] 9. Write positive and negative conformance test: BPMN task with external worker type / indexing repo A alone / deferred reference is stored without reading repo B
- [x] 10. Write positive and negative conformance test: BPMN document with external XML entity / parsing / no network/file expansion occurs
- [x] 11. Write positive and negative conformance test: Malformed BPMN XML / indexing / diagnostics and partial coverage are saved, no false flow links
- [x] 12. Prove repository-scoped incremental behavior and no cross-repository resolution during ingestion.
- [x] 13. Add PostgreSQL 15 integration test from fixture through published UCM; do not duplicate Java/SQL analyzers.
- [x] 14. Update docs with supported versions, limitations, evidence, coverage and error behavior.
- [x] 15. Run ruff check/format, pytest and mandatory CI before checking tasks.

## Acceptance evidence

- `tests/test_bpmn_adapter.py`: 22 passing tests for gateway/guards, metadata,
  worker/process selectors, namespace and UTF-8 ranges, malformed/duplicate IDs,
  DTD/XXE and resource limits; filesystem/network access is explicitly blocked
  in the XXE conformance test.
- `tests/integration/test_bpmn_storage.py`: PostgreSQL 15 publish/read/reuse,
  file-local invalidation, deletion, separate repository with the remote process,
  producer failure and immutable published facts; targeted test passes.
- `docs/bpmn-schema.md` defines mapping, versions, limitations and error behavior.
- Final implementation: `b70b6f78e152d76c03765e97c07e5f3a6b1bab36`.
- [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43646257264):
  **882 passed**, no skipped tests; lint, formatting, all migrations against a clean
  database and generated-file/clean-working-tree checks passed.
