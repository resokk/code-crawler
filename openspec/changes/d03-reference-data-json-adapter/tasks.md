# Tasks: Reference dataset JSON adapter

All tasks are open until implemented and tested.

- [ ] 1. Review existing SourceAdapter registry, UCM types, relation registry and schema migration patterns.
- [ ] 2. Define typed entities, references and SourceAnalysis diagnostics for this format.
- [ ] 3. Implement: Detect configurable type-data.json file patterns and validate JSON structure/version.
- [ ] 4. Implement: Extract ReferenceDataset, Field, Record, keys, value types and exact JSON pointers.
- [ ] 5. Implement: Distinguish source presence from runtime load/deployment status.
- [ ] 6. Implement: Apply bounded record handling and partial diagnostics for malformed entries.
- [ ] 7. Implement: Never infer SQL table from the type prefix; preserve identity in repository snapshot.
- [ ] 8. Write positive and negative conformance test: currencies-data.json with records / indexing / dataset is created without declaring table currencies
- [ ] 9. Write positive and negative conformance test: Valid record with code field / reading source evidence / the correct JSON pointer and bytes are available
- [ ] 10. Write positive and negative conformance test: Malformed record / indexing / partial coverage and diagnostic are recorded
- [ ] 11. Write positive and negative conformance test: Data file merely committed / querying load status / deployment is not claimed
- [ ] 12. Prove repository-scoped incremental behavior and no cross-repository resolution during ingestion.
- [ ] 13. Add PostgreSQL 15 integration test from fixture through published UCM; do not duplicate Java/SQL analyzers.
- [ ] 14. Update docs with supported versions, limitations, evidence, coverage and error behavior.
- [ ] 15. Run ruff check/format, pytest and mandatory CI before checking tasks.
