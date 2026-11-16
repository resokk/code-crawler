# Code-crawler: OpenSpec target roadmap (updated 2026-11-15, b5b3f35)

## Status and rules
The original 39 changes are tracked across active `changes/` and completed `archive/` directories, with proposal.md, design.md, specs/<capability>/spec.md and tasks.md. Many features are **already implemented**, and the baseline is now `b5b3f35ee50fcb0d8546af57898a0436ae642415`. Check [development plan v3](../docs/development-plan-v3.md) and [current review](../docs/review-2026-11-15-b5b3f35.md) for accurate status and priorities. Do not reimplement archived changes.

Existing project capabilities: Python 3.12, canonical immutable UCM snapshots in PostgreSQL 15, Java/Groovy/PLPlus, SQL construction/execution/lineage, ORM, source archive, incremental CLI and publication, structural/lexical search, stateless read-only FastMCP. Confirmed recent GitHub Actions PG15 succeeded on baseline. Reuse these implementations; do not reimplement them.

## Stream A — correctness/security (before corporate deployment)
- A01 safe-snapshot-gc: explicit UCM GC table allowlist and rollback — [completed](archive/2026-11-15-a01-safe-snapshot-gc/completion.md), PG15 CI 1112 passed
- A02 mcp-repository-access-control: principal authentication and repository ACL — [completed](archive/2026-11-15-a02-mcp-repository-access-control/completion.md), PG15 CI 1252 passed
- A03 database-qualified-structural-search: database/version/object scoped SQL access search — [completed](archive/2026-11-16-a03-database-qualified-structural-search/completion.md), PG15 CI 1284 passed
- A04 sql-search-certainty-contract: discovered SQL versus proven execution and target identity
- A05 required-main-ci-check: main branch required status check, requires GitHub admin settings
- A06 source-data-security-policy: raw evidence ACL, redaction of search/embedding inputs

## Stream B — performance/reliability (measure first)
- B01 pg15-end-to-end-performance-baseline: current SHA measurements at scale
- B02 bounded-memory-snapshot-validation: streamed semantic readiness
- B03 short-transaction-indexing: move CPU analysis outside long DB writes
- B04 bulk-load-fk-optimization: evidence-backed PG15 transfer/FK tuning
- B05 incremental-streaming-pipeline: bounded in-flight analysis+clone+staging
- B06 large-snapshot-gc-performance: locks, WAL, orphan blob cleanup
- B07 mixed-language-incremental-regression: real Java/Groovy/PLPlus fixture
- B08 multi-repository-load-and-concurrency: >=100 independent repos

## Stream C — discovery/GraphRAG
- C01 search-document-persistence: versioned derived document generations — [completed](archive/2026-11-15-c01-search-document-persistence/completion.md), PG15 CI passed
- C02 global-discovery-catalog: [completed](archive/2026-11-15-c02-global-discovery-catalog/completion.md), versioned authorized declaration catalog
- C03 repository-version-context: [completed](archive/2026-11-15-c03-repository-version-context/completion.md), immutable latest/pinned/deployment manifests and retention
- C04 external-reference-candidate-search: [completed](archive/2026-11-15-c04-external-reference-candidate-search/completion.md), bounded identity resolution with Evidence
- C05 resolver-cache-and-invalidation: [completed](archive/2026-11-15-c05-resolver-cache-and-invalidation/completion.md), versioned PostgreSQL cache with read-only requests and bounded maintenance
- C06 cross-repository-graph-query: [completed](archive/2026-11-15-c06-cross-repository-graph-query/completion.md), bounded authorized traversal with explicit versions and evidence
- C07 embedding-generation-pipeline: model choice, vector registry/cache and pgvector
- C08 hybrid-retrieval: exact + FTS + vector + graph expansion
- C09 mcp-multirepository-intelligence: global search/trace/impact tools
- C10 kafka-topic-discovery: exact discovery from D07 declaration producers only; new follow-up
- C11 bpmn-worker-discovery: candidate-only worker definitions from D02; new follow-up
- C12 streaming-search-document-rebuild: bounded C01 projections; new follow-up

## Stream D — source adapters (can run parallel with C after stable core)
- D01 bpmn-schema-adapter: BPMN 2.0 processes, elements, flows and variables — [completed](archive/2026-11-15-d01-bpmn-schema-adapter/completion.md), PG15 CI 882 passed
- D02 bpmn-java-bindings: Camunda/Flowable delegates/workers — [completed](archive/2026-11-15-d02-bpmn-java-bindings/completion.md), PG15 CI 997 passed
- D03 reference-data-json-adapter: type-data.json datasets, fields, records
- D04 reference-data-loader-analysis: loader/field/SQL/column lineage
- D05 openapi-contract-adapter: OAS 3.0/3.1/3.2 typed contracts, refs and operations — [completed](archive/2026-11-15-d05-openapi-contract-adapter/completion.md), PG15 CI 1028 passed
- D06 openapi-java-bindings: Spring REST, Feign and ExternalReference — [completed](archive/2026-11-15-d06-openapi-java-bindings/completion.md), PG15 CI 1237 passed
- D07 kafka-message-intelligence: producer/consumer/topic resources — [completed](archive/2026-11-15-d07-kafka-message-intelligence/completion.md), PG15 CI 1171 passed
- D08 graphql-schema-adapter: SDL/introspection, types and operations
- D09 graphql-java-bindings: GraphQL resolvers and DataFetchers
- D10 kotlin-ucm-adapter: Kotlin symbols/calls/interoperability — [completed tasks](archive/2026-11-15-d10-kotlin-ucm-adapter/tasks.md)
- D11 javascript-typescript-ucm-adapters: imports, symbols, HTTP clients — [completed tasks](archive/2026-11-15-d11-javascript-typescript-ucm-adapters/tasks.md)
- D12 vbscript-ucm-adapter: symbols, late binding and SQL patterns — [completed](archive/2026-11-15-d12-vbscript-ucm-adapter/completion.md), PG15 CI 1094 passed

## Stream E — production readiness
- E01 observability-and-coverage-dashboard: job/adapter/search diagnostics
- E02 snapshot-retention-policy: pins, generations and shared blobs
- E03 backup-restore-validation: consistent PG15, UCM source evidence recovery
- E04 openspec-archive-policy: preserve proposal/design/spec/task history

## Critical path
1. **Immediate safety**: A01 completed; A02 open as [PR #8](https://github.com/resokk/code-crawler/pull/8) and MUST precede network MCP exposure; A05 admin-bypass policy and A06 redaction remain open.
2. **Performance**: >1M snapshot indexing now succeeds (405.4s index + 213.2s validation, 1012MiB); B06 GC (~123s/141k) is urgent, B02 SQL validation remains partially memory-bound, B03/B05 follow; B07/B08 for regression/load.
3. **Search**: C01–C06 completed; C10/C11 fill missing typed discovery coverage. C07 (after A06) → C08 → C09 (after A02). C12 removes full UCM materialization from document generation.
4. **Adapters**: D01 → D02; D03 → D04; D05 → D06; D08 → D09; D07/D10/D11/D12 independent after registry readiness. Avoid cross-repo links at ingestion.
5. **Operations**: E01–E04 after corresponding data/ACL boundaries, and E02 before destructive large-scale GC.

## Invariants and Definition of Done
- One repository indexed without consulting other repository indexes. ExternalReference resolved only at query time and in explicit version context.
- All tables in public using ucm_, ingest_, search_, resolver_ prefixes; PostgreSQL 15, pgvector 0.8.0 and currently approved extensions only.
- Published canonical snapshots immutable; search/discovery/vector/resolver state is derived and versioned.
- SQL literal/construction is not SQL execution; embeddings/name similarity are not proof of a CALLS/DB relation.
- Every inferred relation exposes Evidence, Certainty, Coverage, Resolution and supports explicit partial/ambiguous states.
- No change is complete until its scenarios have positive/negative tests, PostgreSQL integration when needed, green CI, docs and checked tasks.md.
- Archive completed specs rather than deleting them. Never merge a speculative reimplementation of already working components merely to satisfy this roadmap.

See [Agent execution guide](AGENT-EXECUTION.md) for the one-change-at-a-time workflow.
