# Tasks: OpenAPI 3.x contract adapter

All tasks are open until implemented and tested.

- [ ] 1. Review existing SourceAdapter registry, UCM types, relation registry and schema migration patterns.
- [ ] 2. Define typed entities, references and SourceAnalysis diagnostics for this format.
- [ ] 3. Implement: Discover YAML/JSON by root openapi field; support dialect-aware OpenAPI 3.0, 3.1 and 3.2.
- [ ] 4. Implement: Extract operations, params, body, responses, schemas, fields, media types, security, callbacks and webhooks.
- [ ] 5. Implement: Support composition, discriminator, required/nullable and recursive local references without unbounded expansion.
- [ ] 6. Implement: Support OpenAPI 3.2 QUERY, additionalOperations and querystring; preserve unsupported vendor extensions with diagnostics.
- [ ] 7. Implement: Resolve local and repository-relative refs; keep remote URI references deferred with no network access.
- [ ] 8. Write positive and negative conformance test: OpenAPI 3.0/3.1/3.2 examples / parsing / version-specific meanings are retained
- [ ] 9. Write positive and negative conformance test: Node schema self-reference / parsing / finite reference graph is generated
- [ ] 10. Write positive and negative conformance test: Remote HTTPS ref / indexing / deferred schema reference is stored without network call
- [ ] 11. Write positive and negative conformance test: OpenAPI 3.2 QUERY and querystring / indexing / typed operation and parameter survive
- [ ] 12. Write positive and negative conformance test: OpenAPI GET endpoint / reading UCM / path, method and source evidence are available
- [ ] 13. Prove repository-scoped incremental behavior and no cross-repository resolution during ingestion.
- [ ] 14. Add PostgreSQL 15 integration test from fixture through published UCM; do not duplicate Java/SQL analyzers.
- [ ] 15. Update docs with supported versions, limitations, evidence, coverage and error behavior.
- [ ] 16. Run ruff check/format, pytest and mandatory CI before checking tasks.
