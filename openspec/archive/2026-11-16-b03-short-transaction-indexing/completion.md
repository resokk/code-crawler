# B03 completion receipt

Implementation: [`0844725`](https://github.com/resokk/code-crawler/commit/0844725266b8f95d603b52a5d4f39cd75a5f1397).
[Required PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/43925216239)
succeeded: **1336 passed in 254.52s**, with Ruff, formatting, clean migrations and
clean-working-tree checks. Local full suite before the final behavior-only test
and concurrent B01 runner integration: 1324 passed. Final focused benchmark/short-
transaction suite: 14 passed; existing incremental suite: 8 passed.

The behavior-only test fails on parent 2951af8 specifically because analysis runs
inside the write transaction. New tests cover idle/no-xmin analysis under PG15
idle_in_transaction_session_timeout, private anonymous spool permissions/closure,
exact baseline reuse while concurrent publication/GC runs, stale CAS rejection,
analysis/spool/stage/transfer failures, changes during archive/final checks,
cancellation and actual process kill. Cancelled nested lease acquisition preserves
the outer owner's lock count. Source/fact readers remain unchanged.

Controlled benchmark: parent 6eaa984 vs 0844725, 400 Java files / 140717 entities,
identical fixture/harness/normalized canonical digest, both validated. Maximum
sampled transaction age: 72.03 -> 25.11 seconds; callbacks inside transaction:
7/7 -> 0/7. Total index: 72.05 -> 70.46 seconds. Peak client RSS: 405.74 -> 428.97
MiB (+5.7%); spool 64191473 bytes. One ordered sample per variant, no throughput/
RAM SLA. Raw environment/settings/code hashes: docs/benchmarks/b03-transactions-pg15.json.

No migration or adapter contract change. Snapshot creation, COPY/clone/archive/
manifests/FK checks and final source verification are atomic. Raw normalized facts
use only a private anonymous process-owned spool; it is not an external pickle
input or a persistent resumable job. Captured bytes/catalogs, per-file worst-case
memory and potentially long write I/O remain B05/other scale work. Existing job
retry starts fresh after crash; no named spool cleanup is required.
Full behavior, metrics and reproduction: docs/ucm-incremental.md.
