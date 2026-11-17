# Java SQL path budget/report completion receipt

Implementation: [`9c2de83`](https://github.com/resokk/code-crawler/commit/9c2de839e49a24d8bde4a3978f7fad98bc5ce3e2).
[Required PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/44160893403)
passed: **1463 tests in 197.74s**, migrations, lint/format and clean-working-tree
checks. Local full suite: 1213 passed / 250 PostgreSQL tests skipped (19.13s).
Local mandatory PG15 report/retry plus execution/JPA storage: 5 passed (7.43s).
PR: https://github.com/resokk/code-crawler/pull/21.

Delivered: canonical index/index-sources flags --java-sql-max-paths (1..65536,
default 256) and optional --java-sql-path-report JSONL. Settings propagate through
all SQL-derived profiles, source adapter and standalone APIs. Per-flow budgets
avoid global mutation; effective budgets enter Java analysis identity. New jobs
persist resolved root/report path and budget; actual retry restores those settings.

Cases identify truncated methods/constructors even with no SQL, with path/hash,
canonical owner/name, coordinates, retained paths and pruning/attempted-lower-bound
counts. Exact-boundary methods are not cases. Reporter memory streams to a private
spool; atomic 0600 export runs before publication. Failed export preserves the old
publication and records the built snapshot on the failed job. Failure/cancellation
best effort reporting preserves the original error and seals late callbacks.

Acceptance: tests/test_sql_path_options.py covers invalid/one/odd/exact/default
budgets, all derived profiles, independent concurrent settings, no-SQL overflow,
fact equivalence with/without callbacks, identity, private atomic output, source-root
preflight, original-error preservation and cancellation. tests/test_cli.py checks
flag parsing and invalid values before execution. tests/integration/test_sql_path_report.py
runs real CLI publication, no-change reuse, budget invalidation, export-failure
pointer preservation and successful retry with restored budget/output path.

Limits: report scope is reanalyzed methods only, not a full repository census;
parser/catalog fallback and reused facts may emit no cases. Attempted counts are
lower bounds for abstract states, not exact feasible runtime path counts. Export
ANALYZED status describes BUILDING snapshot analysis, not publication. Hard process
termination can lose unexported observations. Higher budgets may greatly increase
CPU/RSS and do not bound intermediate allocations. No migration, literal pruning,
path merging or new execution inference. Default budget encoding may trigger one
initial Java reanalysis after upgrade. Contract: docs/java-sql-path-budget.md.
PR remains unmerged.
