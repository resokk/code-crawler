# Tasks: Reference data loader and DB mappings

All tasks are open until implemented and tested.

- [ ] 1. Review existing SourceAdapter registry, UCM types, relation registry and schema migration patterns.
- [ ] 2. Define typed entities, references and SourceAnalysis diagnostics for this format.
- [ ] 3. Implement: Find supported Java/Groovy/PLPlus loader patterns and their dataset identity.
- [ ] 4. Implement: Extract DataLoadOperation and DataLoadMapping with field paths, transformations and DB-context provenance.
- [ ] 5. Implement: Link to existing SQL_EXECUTE, ORM and DATA_ACCESS facts instead of building a duplicate SQL graph.
- [ ] 6. Implement: For reflection/dynamic mapping return PARTIAL/UNKNOWN and evidence, not guessed targets.
- [ ] 7. Implement: For external loader references emit deferred lookup keys.
- [ ] 8. Write positive and negative conformance test: Loader maps field code into target column / analyzing / ReferenceField to DB column path with mapping evidence exists
- [ ] 9. Write positive and negative conformance test: Dynamic reflective field transformation / analyzing / target remains PARTIAL without false resolved column
- [ ] 10. Write positive and negative conformance test: Loader contains SQL INSERT / indexing / statement is discovered but never executed by crawler
- [ ] 11. Write positive and negative conformance test: Dataset in A and loader in B / indexing A / no cross-repository scan occurs
- [ ] 12. Prove repository-scoped incremental behavior and no cross-repository resolution during ingestion.
- [ ] 13. Add PostgreSQL 15 integration test from fixture through published UCM; do not duplicate Java/SQL analyzers.
- [ ] 14. Update docs with supported versions, limitations, evidence, coverage and error behavior.
- [ ] 15. Run ruff check/format, pytest and mandatory CI before checking tasks.
