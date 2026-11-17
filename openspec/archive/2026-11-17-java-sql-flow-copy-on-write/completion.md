# Java SQL flow copy-on-write completion receipt

Implementation: [`e1a0317`](https://github.com/resokk/code-crawler/commit/e1a0317cf9f619d508264baf7ce655dc28c141a0).
[Required PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/44117355425)
passed: **1414 tests in 370.70s**, all migrations, lint/format and clean-working-tree
checks. Local mandatory PG15 full suite: **1414 passed in 481.66s**. Focused Java,
SQL construction/execution and COW regressions: **88 passed**. PR: https://github.com/resokk/code-crawler/pull/19.

The read-only sharing regression was run unchanged on baseline d07a14d and failed
on eager materialization (binding dictionaries differ), not on missing APIs.
Full UcmBatch JSON equals the eager-deepcopy reference on 24 construction cases
(two budgets), plus four JDBC preview/sink cases. Direct tests cover first-write
isolation, both variable/value aliases, saved shadowed bindings and scope exit.
Twelve additional construction payloads match current main's optimized clone.

Controlled fixed-corpus benchmark (same current analyzer with swapped clone
strategies, same 256-path budget, one fresh-process run per mode/case):
- Read-heavy: current main 1.9968s -> COW 0.1801s; materializations 3070 -> 0;
  RSS 79.07 -> 53.93 MiB.
- Write-heavy: 0.2418s -> 0.2472s (2.2% slower); materializations 1022 -> 1022;
  RSS 57.21 -> 56.51 MiB.
- Full fact digests match in current-main, historical deepcopy and COW modes.

Raw report: docs/benchmarks/java-sql-flow-cow-2026-11-17.json contains complete fact,
fixture and source hashes, timing, RSS, host/cgroup and process I/O counts. No real
repository throughput or memory SLA is asserted. Benchmark code loads only the
clone method from a fixed inspected Git commit, requiring that local Git object.

Path ordering/limit/truncation reasons are unchanged. No literal heuristic,
equivalent-state merging, new SQL execution inference or schema migration.
Legacy helper hooks are no-op; existing builder alias uncertainty remains partial.
Internal writes must pass _writable; nested RHS calls reacquire current bindings.
Contract and limits: docs/sql-construction.md. PR remains unmerged.
