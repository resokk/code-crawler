# План развития code-crawler v3 — состояние main b5b3f35 (2026-11-15)

## Назначение

План составлен по [обновлённому code review](review-2026-11-15-b5b3f35.md), а не по исходному прототипу. У существующих changes сохраняются `proposal.md / design.md / specs/<capability>/spec.md / tasks.md`; завершённые changes представлены в `openspec/archive/`. Не реализовывать повторно подтверждённые текущим main компоненты. Новые follow-ups добавляются отдельными OpenSpec changes. Все dates и acceptance относятся к указанному SHA; при сдвиге main проводить diff.

## Статус больших потоков

| Группа | Уже в main | Что ещё открыто |
| --- | --- | --- |
| A Security/Correctness | A01 safe GC | A02 открыт PR #8; A03 DB-qualified SQL search [done]; A04 certainty [done]; A05 strict no-bypass; A06 redaction |
| B Scale/Operations | Sliced indexing, server-side cloning, PG15 1.06M, sliced validation, B04 FK/staging tuning | B01 formal CI performance baseline; B02 SQL invariants; B03 short transactions; B05 true bounded pipeline; B06 GC; B07/08 mixed/100 repos |
| C Search/Graph | C01–C06 complete | C07 embeddings/model selection, C08 hybrid retrieval, C09 MCP global; C10 Kafka and C11 BPMN worker discovery integration; C12 memory-bounded document rebuild |
| D Adapters | D01/D02 BPMN; D05/D06 OpenAPI; D07 Kafka; D10 Kotlin; D11 JS/TS; D12 VBScript | D03/D04 reference JSON + loaders; D08/D09 GraphQL schema + Java; increase partial coverage based on tests |
| E Prod | Some OpenSpec archive operations | E01 metrics, E02 retention, E03 restore; E04 verify archive policy |

## Wave 0 — correctness and network deployment gate

### A02: auth and repository ACL (P0 before HTTP deployment)
Merge/review [PR #8](https://github.com/resokk/code-crawler/pull/8) only after PG15 CI, concurrent-principal auth tests, denied Evidence, error redaction and production token/audit setup are verified. Main is anonymous until merge. No client-supplied grant elevation.

### A05: non-bypass CI protection (P0 org governance)
Keep mandatory `PostgreSQL 15` check. Administrator must require PR and protect against bypass (or document approved exception), test one failed/missing/successful PR. Cannot close based solely on a green push CI.

### A06: source and projection secret policy (P0 before embeddings)
Decide who may read original Evidence vs redacted search/embedding documents. Implement secret policy, approved redaction and non-leaking diagnostics; test concurrent repo ACL, known secrets and false positives.

### A03 and A04: SQL retrieval correctness (P1)
- A03 [done](../openspec/archive/2026-11-16-a03-database-qualified-structural-search/completion.md): exact physical DB/version/object mode distinct from syntactic table-name search; honor quoted identifiers and unbound/ambiguous targets.
- A04 [done]: SQL discovery, execution linkage and DB resolution are independent; an unused `DELETE` is NOT_ESTABLISHED. Evidence/Coverage and canonical certainty are preserved. [Acceptance and PG15 CI](../openspec/archive/2026-11-16-a04-sql-search-certainty-contract/completion.md).
- Required tests: two databases both containing `public.orders`, quoted identifiers, partial and ambiguous execution, cross-snapshot version isolation.

## Wave 1 — performance, with one known serious bottleneck

### B06 first: GC performance (P1 high)
Use 141k PG15 baseline: ~123 s GC vs ~25 s batch-copy. Diagnose FK triggers and missing supporting indexes under actual workload, compare index cost on writes with bounded deletion plan. Verify pinned snapshots, concurrent readers, no unmanaged tables, no orphan sources. Measure GC at 1M; do not extrapolate from one smaller benchmark as an SLA.

### B02: bounded validation (P1)
Already partially implemented: 141k validation ~170 MiB, 17.8s instead of 688 MiB, 4.8s. Remove all-SQL-facts collection from `check_semantics` using SQL/streaming invariants; prove equivalence with original UcmBatch for all invalid SQL/ORM/reference fixtures. Track peak RAM and seconds on SQL-dense workload.

### B03 and B05: short transactions and bounded throughput (P1)
Separate CPU parsing from PostgreSQL write transaction; keep capture immutability verification, CAS and rollback. Bound inflight budget by entities/bytes, not only 64 files. Reuse server-side cloning, temp staging and source archival. Include cancellation and concurrent publication tests.

### B01/B04/B07/B08: measured regression coverage (P1)
Treat successful 1M benchmark as a **completed milestone**, not a reason to mark all baseline tasks complete. Add controlled PG15 400/1000/3000-file runs, end-to-end stage budgets, FK/WAL/GC, compare mixed-language full vs incremental and 100+ concurrent repository publications. Limit new optimizations to measured bottlenecks.

B04 is complete: fresh-table FK plans, per-slice fact staging, C/en_US measurements and two synthetic 1M full-cycle repetitions within 900 s on PG15/tmpfs. [Acceptance and CI](../openspec/archive/2026-11-16-b04-bulk-load-fk-optimization/completion.md). Parser, production-disk, mixed-language and concurrent-repository baselines remain B01/B07/B08 work.

### C12: bounded search document rebuild (P1)
Current C01 storage rebuild materializes full snapshot via `load_snapshot_batch`. Stream projection with bounded batches and atomic generation swap while preserving authorization, redaction, deterministic hashes and old generation on failure.

## Wave 2 — complete discovery with new source producers

### C10: Kafka topic discovery (P1)
D07 produces static topic declarations; C02 still says KAFKA_TOPIC UNSUPPORTED. Project only verifiable typed topic **definitions** with explicit cluster/environment identity or PARTIAL identity when absent; do not turn subscriptions/producer expressions into deployment proof. Add exact keys and bounded C04 selectors with ambiguity and Evidence.

### C11: BPMN worker discovery (P1)
Extract declaration identities supported by D02, distinguish worker handler definitions vs external worker references. Publish only typed definitions with framework/namespace context. Ambiguity and runtime deployment remain PARTIAL; don't fabricate RESOLVED for name-only matches.

## Wave 3 — useful GraphRAG/MCP

1. C07 select embedding model for RU/EN, code/schema/SQL, latency/memory and pgvector 0.8.0 limits. Use redacted C01 documents; model/preprocessing version and content cache, partial generations.
2. C08 merge exact identifier, FTS/trigram, vector candidates and bounded graph expansion with explainable ranking. Semantic similarity is not a confirmed relation; evaluate on labelled developer queries.
3. C09 MCP global search, resolve, impact with explicit version contexts, principal grants, fanout/time bounds, evidence and partial status. Reuse existing C02–C06; no duplicate graph.

## Wave 4 — business adapters and hardening

1. D03 → D04 reference data JSON, typed keys/fields/records and loader → SQL/ORM → DB column; never infer table from dataset filename or runtime deployment from source data.
2. D08 → D09 GraphQL SDL/introspection, composed schema/root operations, Spring/Java DataFetcher binding. Nested-field handlers, ambiguity, federation and source provenance.
3. D10/D11/D12 follow-up coverage: Kotlin scripts/Java interop/SQL lineage, TS config aliases/type checker limitations, VBScript host/ADODB edge cases. Preserve PARTIAL coverage, don't rebuild parser infrastructure.
4. E01 metrics and Coverage dashboard; E02 pinned retention/source blobs/derived generations and E03 backup/restore on clean PG15. E04 preserve archived completed specifications and supporting CI receipts.

## Execution order / dependencies

`A02 (PR #8) + A05 + A06` → trusted multi-user MCP/embeddings; `B06` can run independently after A01; `A03 → A04` is a search correctness lane; `B02 → B03 → B05` is the indexing lane; `C01–C06 [done] → C10/C11 and C07 → C08 → C09`; D03→D04 and D08→D09 parallel after SourceAdapter registry. E02 must precede any aggressive GC optimization.

## Definition of Done

- One change per LLM session and implementation PR. Existing `AGENTS.md` workflow, no speculative refactor or reimplementation.
- Full proposal/design/spec (MUST/SHOULD, Given/When/Then), tasks, compatibility and tests including negative cases.
- PostgreSQL 15 migration and integration tests where needed, green mandatory CI and source/Evidence integrity; no cross-snapshot FK or global resolution at ingest.
- No false definite SQL execution/DB target/runtime Kafka/HTTP relationship; preserve Certainty, Coverage, Resolution, Evidence and independent repository publication.
- Current published snapshot preserved across ingest, validation, GC, search generation and resolver failures.
- Archive only after acceptance tests and completion evidence; keep unfinished criteria active.
