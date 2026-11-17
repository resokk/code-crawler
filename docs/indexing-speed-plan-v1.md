# План ускорения индексации code-crawler v1

**Исходный код:** `main@1616781acb871bd50a5e67a1184b4371b3322a4f` (2026-11-17). **Статус:** 11 OpenSpec changes B09–B19 созданы, ещё не реализованы.

## Что уже сделано и не нужно повторять

- B01 PostgreSQL 15 benchmark, B02 bounded-memory readiness, B03 CPU-analysis outside write transactions, B04 bounded per-slice staging and fresh planner stats; existing B05 continues bounded end-to-end pipeline, B06 is snapshot GC rather than new-index throughput.
- Java analyzer: SQL state copy-on-write, bounded per-file decoded-text cache, `--java-sql-max-paths` (default 256), overflow diagnostics, `--analysis-workers` 1..32 (default 1).
- C12 streaming search document rebuild now exists in current source; don't propose duplicating it as indexing throughput optimization.

## Measured basis, limitations

- B01 independent PG15/2CPU/8GiB baseline at commit `6eaa984`: 400 Java files / 140717 entities, **92.576s indexing** + **43.132s validation** median of 3; 1000 files / 352817 entities, 258.442s + 130.865s single run. 3002-file attempt stopped by disk reserve and cannot be used as a completed >1M result. The historical successful 1.06M test was on a different machine and code. [Evidence](performance-baseline.md).
- Breakdown of 400-file **indexing**, not additive to validation: analyze 37.298s, stage 2.748s, transfer 15.758s, FK 10.761s, prepare 3.784s, capture 0.033s; remaining ~32.2s covers row conversion, snapshot/manifest/verification/overhead. Nested times cannot be summed naïvely.
- Existing parallel Java feature on 2-CPU quota: small corpus 1 worker 0.019s vs 2 workers 0.725s; CPU-heavy 1 worker 6.008s vs 2 workers 3.811s; catalog-heavy 1 worker 6.138s vs 2 workers 8.805s. Four workers underperformed in all three fixtures. This is one fresh-process run/case, not production default guidance. [Evidence](parallel-snapshot-preparation.md).
- B03 sampled write transaction on 400 files 72.03 → 25.11s; overall indexing 72.05 → 70.46s, spool ~64MB and parent RSS +5.7%, single controlled comparison. Optimization shifted time/space, it did not make full indexing dramatically faster.

## Priority queue

| Order | Change | Purpose | Relative expected benefit / caveat |
| --- | --- | --- | --- |
| 1 | **B09** Critical path profiler | Current full-stage CPU/memory/IO measurements on HEAD, not stale benchmark | Necessary to avoid optimizing wrong phase |
| 2 | **B19** Performance regression gates | Reproducible and low-noise algorithmic counters plus dedicated PG15 runs | Protect future speedups and canonical semantic parity |
| 3 | **B10** Worker catalog reuse | Avoid repeated expensive full catalogs in each Python subprocess | Evidence: catalog-heavy 2 workers slower and more RAM |
| 4 | **B11** Cost-aware scheduling | Avoid IPC/startup overhead for light work; balance heavy files | Evidence: CPU-heavy gains with 2 workers only |
| 5 | **B15** Normalize/serialize UCM | Profile and remove redundant Pydantic→dict→pickle→tuple materialization | Likely CPU/alloc savings, requires proof |
| 6 | **B16** Adaptive PG stage/transfer | Fewer expensive small COPY/INSERT/TRUNCATE ops while retaining FK | Material impact candidate: 15.8s transfer baseline |
| 7 | **B17** Readiness latency tuning | Speed up SQL/global invariant validation without all-SQL hydration | Candidate: 43.1s baseline; use fresh B02 SHA |
| 8 | **B18** Unchanged snapshot no-op | Save clone+validation on truly unchanged reindex; explicit opt-in | Major potential benefit for polling, changes semantics only under explicit mode |
| 9 | **B12** AST reuse | Eliminate repeated Java parsing only if profiler shows it | Don't over-design existing AST caching |
| 10 | **B13** SQLGlot cache | Exploit duplicate exact SQL/dialect parsing | High benefit only if duplicate ratio sufficient |
| 11 | **B14** SQL/ORM shared read-only flow | Reduce repeated method traversals | Highest semantic risk; defer until proven |

## Delivery strategy

1. **Measurement lane** B09→B19. Freeze baseline current HEAD, fixtures and resource budgets. Run several before/after trials; record source SHA, dependency hash, PG settings, quota, warm/cold effects and false regressions.
2. **Java lane** B10/B11; then conditional B12→B13/B14. Preserve source diagnostics, overload ambiguity, partial SQL, Evidence and versioning. Keep workers=1 baseline; never enable 4 workers by default on 2-core host.
3. **Storage lane** B15/B16/B17; coordinate B16 with active B05. No disabling PostgreSQL FK or relaxing UCM validators to reduce latency.
4. **Incremental lane** B18 opt-in strict unchanged-publication reuse after signature/version/commit checks; existing clone path is retained for callers that require fresh snapshot ID.
5. **Fleet lane** existing B07/B08 on mixed languages and 100+ repos; use the speed suite, not just unit-level microbenchmarks.

## Acceptance checklist for every change

- Positive, negative, cancellation and corruption scenarios; PostgreSQL 15 integration where appropriate.
- Exact canonical digest, Evidence/SourceRange, Coverage, SQL certainty and snapshot publication parity.
- No additional cross-repository linking during local ingest and no secret leakage through performance logs.
- Bounded RAM/spool/temp/IPC budgets and fail-safe cleanup.
- Multiple-sample wall/CPU/RSS/IO/WAL report; no blanket speedup claim without data.
- One feature per PR, check OpenSpec tasks only after CI/benchmark; archive with completion receipt.
