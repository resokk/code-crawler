# Tasks: OpenAPI to Spring handlers and Feign clients

Verified implementation and acceptance evidence: completion.md.

- [x] 1. Review existing SourceAdapter registry, UCM types, relation registry and schema migration patterns.
- [x] 2. Define typed entities, references and SourceAnalysis diagnostics for this format.
- [x] 3. Implement: Parse effective Spring MVC/WebFlux mappings from class/method annotations including HTTP method, routes, consumes and produces.
- [x] 4. Implement: Derive route candidate keys without losing original path parameter names; include known base/server context.
- [x] 5. Implement: Resolve API operation to Java handler only when route, HTTP method and framework constraints match uniquely.
- [x] 6. Implement: Represent ambiguous controllers as candidates and unresolved or client calls as ExternalReference.
- [x] 7. Implement: Map DTO argument/response types only from signatures and explicit annotations; connect to existing Java Call Graph and SQL.
- [x] 8. Write positive and negative conformance test: Matching OpenAPI GET and Spring GetMapping with class prefix / binding / operation points to one handler with two-source evidence
- [x] 9. Write positive and negative conformance test: GET contract but POST controller / binding / no false RESOLVED relation is created
- [x] 10. Write positive and negative conformance test: Two compatible controllers / binding / status AMBIGUOUS and alternatives are returned
- [x] 11. Write positive and negative conformance test: FeignClient for remote loan-service / indexing / selector includes service, method and path with deferred target
- [x] 12. Write positive and negative conformance test: Handler calls service and SQL / traversal / API to handler to SQL path is accessible
- [x] 13. Prove repository-scoped incremental behavior and no cross-repository resolution during ingestion.
- [x] 14. Add PostgreSQL 15 integration test from fixture through published UCM; do not duplicate Java/SQL analyzers.
- [x] 15. Update docs with supported versions, limitations, evidence, coverage and error behavior.
- [x] 16. Run ruff check/format, pytest and mandatory CI before checking tasks.
