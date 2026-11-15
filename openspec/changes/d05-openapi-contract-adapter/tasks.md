# Tasks: OpenAPI 3.x contract adapter

Acceptance evidence is recorded below; mandatory CI is checked after the implementation run.

- [x] 1. Review existing SourceAdapter registry, UCM types, relation registry and schema migration patterns.
- [x] 2. Define typed entities, references and SourceAnalysis diagnostics for this format.
- [x] 3. Implement: Discover YAML/JSON by root openapi field; support dialect-aware OpenAPI 3.0, 3.1 and 3.2.
- [x] 4. Implement: Extract operations, params, body, responses, schemas, fields, media types, security, callbacks and webhooks.
- [x] 5. Implement: Support composition, discriminator, required/nullable and recursive local references without unbounded expansion.
- [x] 6. Implement: Support OpenAPI 3.2 QUERY, additionalOperations and querystring; preserve unsupported vendor extensions with diagnostics.
- [x] 7. Implement: Resolve local and repository-relative refs; keep remote URI references deferred with no network access.
- [x] 8. Write positive and negative conformance test: OpenAPI 3.0/3.1/3.2 examples / parsing / version-specific meanings are retained
- [x] 9. Write positive and negative conformance test: Node schema self-reference / parsing / finite reference graph is generated
- [x] 10. Write positive and negative conformance test: Remote HTTPS ref / indexing / deferred schema reference is stored without network call
- [x] 11. Write positive and negative conformance test: OpenAPI 3.2 QUERY and querystring / indexing / typed operation and parameter survive
- [x] 12. Write positive and negative conformance test: OpenAPI GET endpoint / reading UCM / path, method and source evidence are available
- [x] 13. Prove repository-scoped incremental behavior and no cross-repository resolution during ingestion.
- [x] 14. Add PostgreSQL 15 integration test from fixture through published UCM; do not duplicate Java/SQL analyzers.
- [x] 15. Update docs with supported versions, limitations, evidence, coverage and error behavior.
- [ ] 16. Run ruff check/format, pytest and mandatory CI before checking tasks.


## Acceptance evidence

2026-11-15, local PostgreSQL 15 (Docker postgres:15), after rebasing onto C02/C03/D02:
`uv run ruff check .`, `uv run ruff format --check .`,
`uv run pytest --require-postgres -x -q`: **1025 passed in 136.59s**.
Before upstream rebase the complete suite passed 954 tests.

`tests/test_openapi_adapter.py` covers 3.0/3.1/3.2 syntax, typed operations,
QUERY/additionalOperations/querystring, recursive refs, discriminator mappings,
relative/missing/remote refs, duplicate anchors, base-scope deferral, data-only
examples/extensions, strict JSON, unsafe YAML/paths and parser budgets.
`tests/integration/test_openapi_storage.py` proves PG15 migration/publication,
archived Evidence via published_reader, unchanged reuse, schema edit/delete,
activation of unchanged fragments, independent repositories, TS config coexistence
and producer-failure preservation. Existing JS/TS, C01/C02/C03/D02 suites pass.

Migration is 0025 after incorporating concurrent upstream migrations. The exact
storage, dialect, parser, coverage and unsupported semantics contract is in
docs/openapi-contracts.md. No runtime HTTP/Java binding or remote resolution is
claimed; D06 stays independent.

Final reference-boundary regression: directory-only references and URI control
characters are diagnosed without aborting the producer. Focused PG15 suite:
27 passed. Full final PG15 suite: **1028 passed in 132.53s**; lint and formatting
passed. Initial implementation CI also passed (run 43681365700); final fix CI
is recorded in completion.md after verification.
