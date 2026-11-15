# Design

Migration 0016 adds `ingest_jobs`. `index-sources` records a job after repository
registration, moves it INDEX → PUBLISH and closes it SUCCEEDED or FAILED with a
structured failure (type, message, and for AdapterError the adapter, stage and
per-file diagnostics). Run parameters are stored so a retry needs only the job ID.

Liveness uses a session advisory lock per job instead of heartbeats or timeouts:
a dead process drops it, so `jobs retry` and GC can tell abandoned from running.
Retry is safe because each attempt builds a new BUILDING snapshot and publishes
with CAS on its own base pointer.

`snapshot gc` runs in one transaction: reap abandoned jobs, delete BUILDING
snapshots older than a threshold whose repository has no running job, and delete
RETIRED snapshots beyond the N most recent per repository. Fact guards stay; they
allow DELETE for RETIRED only under transaction-local `code_crawler.gc = 'on'`.
PUBLISHED, READY and VALIDATING are never deleted. No scheduler: retention is an
explicit operator command. Stages inside INDEX are not tracked separately.


GC deletes only the explicit snapshot-owned table registry in `jobs.py`. It does
not discover deletion targets from public columns or table-name prefixes.
`ingest_jobs` survives via ON DELETE SET NULL, publication pointers are protected,
and shared source blobs remain outside snapshot cleanup. A clean-schema integration
test checks registry coverage when migrations add snapshot-owned tables. Foreign
UUID/text snapshot_id tables remain untouched while BUILDING/RETIRED GC completes.

GC timing: deleting a 141k-entity snapshot takes about five times as long as
loading it. The time goes to deferred foreign-key checks at commit; referencing
columns without an index make part of it quadratic. Measured and explained in
docs/ingest-jobs.md; the fix (indexes or batched deletion) belongs to change b06.
