# Tasks: OpenAPI to Spring handlers and Feign clients

All tasks are open until implemented and tested.

- [ ] 1. Review existing SourceAdapter registry, UCM types, relation registry and schema migration patterns.
- [ ] 2. Define typed entities, references and SourceAnalysis diagnostics for this format.
- [ ] 3. Implement: Parse effective Spring MVC/WebFlux mappings from class/method annotations including HTTP method, routes, consumes and produces.
- [ ] 4. Implement: Derive route candidate keys without losing original path parameter names; include known base/server context.
- [ ] 5. Implement: Resolve API operation to Java handler only when route, HTTP method and framework constraints match uniquely.
- [ ] 6. Implement: Represent ambiguous controllers as candidates and unresolved or client calls as ExternalReference.
- [ ] 7. Implement: Map DTO argument/response types only from signatures and explicit annotations; connect to existing Java Call Graph and SQL.
- [ ] 8. Write positive and negative conformance test: Matching OpenAPI GET and Spring GetMapping with class prefix / binding / operation points to one handler with two-source evidence
- [ ] 9. Write positive and negative conformance test: GET contract but POST controller / binding / no false RESOLVED relation is created
- [ ] 10. Write positive and negative conformance test: Two compatible controllers / binding / status AMBIGUOUS and alternatives are returned
- [ ] 11. Write positive and negative conformance test: FeignClient for remote loan-service / indexing / selector includes service, method and path with deferred target
- [ ] 12. Write positive and negative conformance test: Handler calls service and SQL / traversal / API to handler to SQL path is accessible
- [ ] 13. Prove repository-scoped incremental behavior and no cross-repository resolution during ingestion.
- [ ] 14. Add PostgreSQL 15 integration test from fixture through published UCM; do not duplicate Java/SQL analyzers.
- [ ] 15. Update docs with supported versions, limitations, evidence, coverage and error behavior.
- [ ] 16. Run ruff check/format, pytest and mandatory CI before checking tasks.
