# Code-crawler: OpenSpec target roadmap (updated 2026-11-17, e133ccc)

## Status and rules

The backlog is tracked in active `openspec/changes` and completed `openspec/archive` with evidence receipts. Latest audited main: `e133cccb65a39fa62615cc484441a6f523ec6973`. See [review 2026-11-17](../docs/review-2026-11-17-e133ccc.md) and [development plan v4](../docs/development-plan-v4.md). A02/A03/A04/A06, B01/B02/B03/B04 and E01 are now implemented; do not reimplement. New A07 is a migration-history/search_path safety follow-up. Successful PG15 CI at [run 44165042979](https://github.com/resokk/code-crawler/actions/runs/44165042979) checks a fresh database but does not establish upgrade compatibility on old populated DB.

Current capabilities: canonical UCM with immutable snapshots, Java/Groovy/PLPlus/Kotlin/JS/TS/VBScript, SQL and ORM, BPMN, OpenAPI, Kafka, independent repository publication, structural/lexical discovery, query-time multi-repo resolver with cache/traversal, read-only authenticated MCP, redaction and monitoring. Unfinished capabilities remain explicitly PARTIAL.

## Stream A — correctness/security (before corporate deployment)
- A01 safe-snapshot-gc: explicit UCM GC table allowlist and rollback — [completed](archive/2026-11-15-a01-safe-snapshot-gc/completion.md), PG15 CI 1112 passed
- A02 mcp-repository-access-control: principal authentication and repository ACL — [completed](archive/2026-11-15-a02-mcp-repository-access-control/completion.md), PG15 CI 1252 passed
- A03 database-qualified-structural-search: database/version/object scoped SQL access search — [completed](archive/2026-11-16-a03-database-qualified-structural-search/completion.md), PG15 CI 1284 passed
- A04 sql-search-certainty-contract: [completed](archive/2026-11-16-a04-sql-search-certainty-contract/completion.md), SQL discovery/execution certainty
- A05 required-main-ci-check: branch protection/no-bypass administrative verification remains active
- A06 source-data-security-policy: raw evidence ACL, redaction of search/embedding inputs — [completed](archive/2026-11-16-a06-source-data-security-policy/completion.md), PG15 CI 1305 passed
- A07 migration-history-and-schema-resolution: NEW — edited historic SQL, no checksums, implicit search_path; upgrade safety

## Stream B — performance/reliability (measure first)
- B01 pg15-end-to-end-performance-baseline: [completed](archive/2026-11-16-b01-pg15-end-to-end-performance-baseline/completion.md), 400/1000-file results and documented >1M-target disk limit; PG15 CI 1325 passed
- B02 [done] bounded-memory-snapshot-validation: SQL/streamed semantic readiness; [acceptance](archive/2026-11-17-b02-bounded-memory-snapshot-validation/completion.md)
- B03 short-transaction-indexing: move CPU analysis outside long DB writes — [completed](archive/2026-11-16-b03-short-transaction-indexing/completion.md), PG15 CI 1336 passed
- java-sql-flow-copy-on-write: lazy Java SQL branch state — [completed](archive/2026-11-17-java-sql-flow-copy-on-write/completion.md), PG15 CI 1414 passed
- java-source-text-cache: bounded worker-local decoded Java text — [completed](archive/2026-11-17-java-source-text-cache/completion.md), PG15 CI 1431 passed
- java-sql-path-budget-report: configurable Java path budget and optional metadata JSONL — [completed](archive/2026-11-17-java-sql-path-budget-report/completion.md), PG15 CI 1463 passed
- parallel-snapshot-preparation: opt-in bounded Java CPU workers — [completed](archive/2026-11-17-parallel-snapshot-preparation/completion.md), PG15 CI 1477 passed
- B04 bulk-load-fk-optimization: [completed](archive/2026-11-16-b04-bulk-load-fk-optimization/completion.md), PG15 plans and bounded per-slice fact staging
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
- C10 kafka-topic-discovery: complete; discovery/3 NewTopic declarations only, exact contextual C04 candidates; [receipt](archive/2026-11-17-c10-kafka-topic-discovery/completion.md)
- C11 bpmn-worker-discovery: complete; typed standalone D02 worker registrations and candidate-only C04 discovery; [receipt](archive/2026-11-17-c11-bpmn-worker-discovery/completion.md)
- C12 streaming-search-document-rebuild: [completed](archive/2026-11-17-c12-streaming-search-document-rebuild/completion.md), full-record parity above 1M facts, 95 MiB streaming RSS; PG15 CI 1489 passed

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
- E01 observability-and-coverage-dashboard: job/adapter/search diagnostics — [completed](archive/2026-11-17-e01-observability-and-coverage-dashboard/completion.md), PG15 CI 1382 passed
- E02 snapshot-retention-policy: pins, generations and shared blobs
- E03 backup-restore-validation: consistent PG15, UCM source evidence recovery
- E04 openspec-archive-policy: preserve proposal/design/spec/task history

## Critical path (revised 2026-11-17)

1. Migration and governance: **A07 first** for upgrading existing databases; **A05** required rules verification.
2. Storage operations: **B06** GC measured above 120s on 141k; coordinate with **E02** retention/source blob lifecycle. B05 bounded spool/staging, C12 bounded search projection [completed]; B07/B08 after.
3. Search: C01–C06 complete; **C10/C11** declaration discovery complete; **C07 → C08 → C09** GraphRAG, with A02/A06 already implemented. No runtime certainty promotion.
4. Adapters: D03→D04 reference-data; D08→D09 GraphQL. Existing D01/D02, D05/D06, D07, D10/D11/D12 done.
5. Ops: E01 done; E02/E03 pending; E04 archive policy, monitoring drift review.

## Invariants and Definition of Done
- One repository indexed without consulting other repository indexes. ExternalReference resolved only at query time and in explicit version context.
- All tables in public using ucm_, ingest_, search_, resolver_ prefixes; PostgreSQL 15, pgvector 0.8.0 and currently approved extensions only.
- Published canonical snapshots immutable; search/discovery/vector/resolver state is derived and versioned.
- SQL literal/construction is not SQL execution; embeddings/name similarity are not proof of a CALLS/DB relation.
- Every inferred relation exposes Evidence, Certainty, Coverage, Resolution and supports explicit partial/ambiguous states.
- No change is complete until its scenarios have positive/negative tests, PostgreSQL integration when needed, green CI, docs and checked tasks.md.
- Archive completed specs rather than deleting them. Never merge a speculative reimplementation of already working components merely to satisfy this roadmap.

See [Agent execution guide](AGENT-EXECUTION.md) for the one-change-at-a-time workflow.
