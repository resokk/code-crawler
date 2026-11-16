# Completion: B01 PostgreSQL 15 end-to-end performance baseline

Measured clean runner: `6eaa9841d9a1b4352ac8714c758d3b684afb8bf3`.
Final evidence, disk reserve and aggregation implementation:
`3de9d3d01f2fb65a75bb24d791af4cfc4cbff146`.

The opt-in runner uses current migrations, deterministic captured Java/JDBC
fixtures, fresh worker processes and only parent-owned disposable databases.
Capture, prepare, analyze, staging, transfer, deferred FK checks, archival, index
total, validation, publication, reader queries, incremental clone and GC are
measured separately. The protocol retains environment/commit/fixture hashes,
client RSS/CPU/IO, PG database/relation statistics, cluster WAL deltas and complete
EXPLAIN ANALYZE BUFFERS JSON plans. No schema, application pipeline or stored
certainty/evidence semantics are changed.

Acceptance evidence:

- Three 400-file trials: 140,717 entities each, index 92.283/92.576/93.094 seconds,
  validation 40.792/43.132/51.347 seconds, client RSS 414.0–419.5 MiB.
- All three GC trials exceeded the explicit 120-second budget. Cancellation
  recovery preserved published pointers and identical reader results. These are
  censored failures, not successful completed-GC timings.
- 1,000 files: 352,817 entities, index 258.442 seconds, validation 130.865 seconds;
  publication/readers completed. The disk supervisor stopped the later clone
  with 528,424,960 bytes free on the shared PGDATA filesystem.
- The 3,002-file >1M-target attempt stopped on transfer at 531,554,304 free bytes.
  Its partial checkpoint and 1,045,068 KiB client peak RSS are retained. No full
  million-entity snapshot, validation/publication, completed GC or OOM is claimed.
  The specification explicitly accepts a documented failed large-scale attempt.
- The supervisor signals only verified direct benchmark workers. The parent
  records SIGTERM exits and removes its own databases; zero owned DBs remained.
- Original collector-v1 JSON is preserved unchanged as gzip. Summary-v2 excludes
  incomplete slice sums from whole-workload distributions; regression tests
  verify this distinction. All failures and all three small-scale samples remain.

Artifacts: [protocol/results](../../../docs/performance-baseline.md),
[compact JSON](../../../docs/benchmarks/end-to-end-pg15-2026-11-16.json),
[full raw report](../../../docs/benchmarks/end-to-end-pg15-2026-11-16.raw.json.gz),
[disk observations](../../../docs/benchmarks/end-to-end-pg15-2026-11-16.disk-guard.json).
Raw report SHA256:
`d0c8c1f6871b9c214cca39c03ae979a2373ff2a9547cf3bc446924f9853a6bdf`.

Validation:

- Ruff lint and formatting: passed (395 files).
- Final focused suite: 14 passed in 13.57s.
- Final local mandatory PG15 full suite: 1325 passed in 314.76s.
- [Required PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/43927411180)
  on final implementation SHA: success, 1325 passed in 291.55s; clean-database
  migrations and generated-file/working-tree checks passed.

This is a synthetic baseline on a 2-CPU/8-GiB container with limited local disk,
not a production SLO or a proven scalability ceiling. More PGDATA/WAL capacity is
needed for a completed current-SHA >1M rerun. B06 GC and B02/B03/B05 indexing work
remain independent follow-ups; this change records rather than hides bottlenecks.
