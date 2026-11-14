# Tasks: BPMN Java handler bindings

Implementation and local conformance/PG15 verification are complete; checkboxes stay open until required CI passes.

- [ ] 1. Review existing SourceAdapter registry, UCM types, relation registry and schema migration patterns.
- [ ] 2. Define typed entities, references and SourceAnalysis diagnostics for this format.
- [ ] 3. Implement: Implement version-aware Camunda and Flowable binding profiles.
- [ ] 4. Implement: Resolve JavaDelegate, delegateExpression, Spring bean, external worker/topic to local Java symbols.
- [ ] 5. Implement: Track process variable mapping as typed facts with uncertain data lineage made explicit.
- [ ] 6. Implement: Create evidence-backed BPMN task to Java handler relations; ambiguous beans remain ambiguous.
- [ ] 7. Implement: Produce ExternalReference selectors for external workers/processes without global lookup.
- [ ] 8. Write positive and negative conformance test: ServiceTask bound to one Spring bean / analyzing / task to handler relation includes BPMN and Java evidence
- [ ] 9. Write positive and negative conformance test: Two compatible delegate beans / binding / AMBIGUOUS with both candidates is returned
- [ ] 10. Write positive and negative conformance test: External worker in another repository / indexing / deferred selector is emitted
- [ ] 11. Write positive and negative conformance test: Delegate invoking SQL / local graph traversal / BPMN to Java to SQL path composes from existing relations
- [ ] 12. Prove repository-scoped incremental behavior and no cross-repository resolution during ingestion.
- [ ] 13. Add PostgreSQL 15 integration test from fixture through published UCM; do not duplicate Java/SQL analyzers.
- [ ] 14. Update docs with supported versions, limitations, evidence, coverage and error behavior.
- [ ] 15. Run ruff check/format, pytest and mandatory CI before checking tasks.

## Acceptance evidence (CI pending)

- `tests/test_bpmn_java_bindings.py`: delegate/Spring bean/worker contracts,
  profile namespace isolation, ambiguous/duplicate registrations, dynamic selectors,
  incomplete Java catalog, typed variables/mappings, AST reuse, inheritance and
  existing Java-to-SQL composition; unrelated XML does not build a Java catalog.
- `tests/test_adapter_catalogs.py`: read-only deterministic binding, duplicate keys,
  typed/deeply frozen exports, captured source ownership/hash/range validation and
  prepared-version drift rejection.
- `tests/integration/test_bpmn_java_storage.py`: PG15 publish/read/trace, CLI profile,
  reuse, added/removed candidate, bean rename, profile-only invalidation, handler
  deletion, parser/binding failure and repository isolation with actual remote targets.
- Full local PG15 suite: 941 passed. Final catalog/variable/root-preflight refinements
  also pass targeted unit and PG15 tests. Ruff check/format pass.
- Supported APIs, versioning and explicit partial lineage are documented in
  `docs/bpmn-java-bindings.md`. Required GitHub Actions verification pending.
