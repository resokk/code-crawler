# Parallel snapshot preparation completion receipt

Implementation: [`94e4f10`](https://github.com/resokk/code-crawler/commit/94e4f10aeb53784586936cac5771603e660d3841).
[Required PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/44175096157)
passed: **1477 tests in 293.87s**, migrations, lint/format and clean-working-tree
checks. Local full suite: 1226 passed / 251 PostgreSQL tests skipped (26.62s).
Local mandatory PG15 preparation/report/short-transaction regressions: 15 passed;
final guarded preparation/report checks: 2 passed. Process/supervision suite:
11 passed, including actual hard-parent-kill with blocked children.
PR: https://github.com/resokk/code-crawler/pull/23.

Delivered: --analysis-workers 1..32 (default 1), saved for retry, optional managed
Java spawn processes, same captured-byte/catalogue/settings version checks, private
typed IPC, bounded source-slice groups and stable result/callback ordering. No AST,
DB handle or report sink crosses IPC. Parent enrichment/normalization/spool and
all canonical writes remain in the parent. Explicit preparation-complete cleanup
stops workers before writes; failure/cancellation/crash and parent-sentinel death
terminate the owned group. Worker count is excluded from analysis identity.

Acceptance: tests/test_java_parallel.py compares complete ORM/HTTP/schema facts,
ordering, version and report events for 1/2/4; verifies source/version mismatch,
abrupt exit, cancellation, hard parent death and process cleanup. CLI tests cover
flag forwarding. PG tests assert no live analysis workers during canonical writes,
reuse with changed worker count, no new snapshot/publication on injected failure,
and path-report/retry compatibility with workers enabled.

Controlled synthetic benchmark, one ordered fresh-process run per mode/case,
CPU quota 2 cores, memory limit 8 GiB; full fact digests match:
- Small: 1/2/4 workers 0.019/0.725/1.260s; aggregate sampled RSS
  47.8/159.1/256.3 MiB.
- CPU case (budget 4096): 6.008/3.811/5.886s; RSS 71.9/210.8/337.3 MiB.
- Catalogue-heavy (budget 256): 6.138/8.805/12.217s; RSS
  213.6/538.5/717.1 MiB.

Raw source/fixture/fact/lock hashes, environment, versions, CPU/I/O and samples:
docs/benchmarks/parallel-preparation-2026-11-17.json. Process-tree discovery runs
once at startup; 25ms samples include parent/descendants/spawn helper with checked
start identities. Summed RSS double-counts shared pages and can miss transient peaks.
Timing includes catalogue/startup/IPC/shutdown, excludes capture, parent row
normalization and DB writes. These are not production or linear-scaling guarantees.

Limits: N additional full catalogues, startup/IPC and serial normalization costs;
symbols/parser fallback and other adapters stay sequential; one file is not split.
Python's idle resource tracker can remain until parent exit. Default remains 1.
Operational contract: docs/parallel-snapshot-preparation.md. No migration or new
execution inference. PR remains unmerged.
