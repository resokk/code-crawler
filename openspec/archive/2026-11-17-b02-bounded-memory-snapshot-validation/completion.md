# Completion: B02 bounded-memory snapshot validation

Implementation: `a3739fbb592a1ff40410c3f65e8be615a8cf3053`.

Readiness no longer hydrates all SQL facts or accumulates paths, producers,
report IDs, parent maps or transitive reference models in Python. Strict entity
hydration uses slices of 2000 and an enforced 20000-model LRU catalog, with batched
one-hop prefetch captured before the destructive renderer and cache hits kept hot.
Global uniqueness, SQL text/partial/origin/binding/context checks use snapshot-scoped
SQL; scope cycles use temporary parent-pointer doubling. Existing model and local
cross-entity validators, ordered rows, subtype/auxiliary consumption, typed FKs,
source archive, ORM and endpoint/Evidence/Coverage rules remain enforced.

Frozen scan runs in REPEATABLE READ with a shared snapshot lease. Cancellation
cooperatively stops reference-batch scheduling and drains the worker before releasing
transaction/connection. Receipt+READY is a separate atomic state-checked transaction.
Concurrent READY returns the stored receipt count; a concurrent publication cannot
create a second receipt or overwrite the publication pointer.

One deliberately strengthened invariant rejects multiple USES_SQL_CONSTRUCTION
descriptors per execution in both reference and SQL validation, replacing the
previous order-dependent last-wins choice. Alternatives belong in one descriptor's
resolution candidates. Existing immutable facts/receipts are not rewritten; explicit
whole-batch restore rejects such legacy malformed graphs if present. Normal
per-entity reader contracts and public ingest/publication signatures are preserved.

Complete rule inventory, compatibility and limits:
[snapshot-validation-invariants.md](../../../docs/snapshot-validation-invariants.md).
No permanent schema migration or new dependency is required. Temporary graph/link
storage and work files depend on graph size/depth; pointer updates can amplify
MVCC storage until transaction end. Model-count bounds are not a byte quota for
one giant entity. Scan deliberately holds a pinned MVCC view for the validation
phase; shortening its lifetime remains B03.

SQL-dense acceptance on PG15.20/Linux, 2-CPU quota/8 GiB, dedicated tmpfs, no concurrent
load: 24002 → 96002 entities (18000 → 72000 SQL models), production cache/slice limits.
Baseline Python heap grows 63.76 → 221.58 MiB; B02 42.95 → 40.38 MiB, factor 0.94.
Preselected growth <1.5 and absolute <128 MiB on this fixture pass. Separate no-trace
96002-entity observations: 22.318 s baseline vs 12.707 s B02; process peak RSS
321.07 vs 92.09 MiB. Traced timings/RSS and exact implementation hashes are retained
in [the measurement artifact](../../../docs/benchmarks/bounded-validation-pg15-2026-11-16.json).
Parser and production-disk throughput are excluded; single observations are not an SLA.

Validation:

- SQL-dense memory regression demonstrably fails on baseline `2951af8` at fixed
  slice64/cache128 (9320231 bytes > 3006458*1.5), passes with B02.
- 29 targeted tests pass: whole-batch/SQL parity on valid and corrupted SQL,
  partial/failed/ambiguous origin, positional/named binding, DB context, producer,
  ORM, deep/cyclic scopes, cancellation/drained reference reads and concurrent state.
  A separate cache-working-set test prevents accidental N+1 prefetch regressions.
- Full mandatory local PG15 suite: 1354 passed (499.64s); later CLI profiler merge
  verified with 17 CLI/profiling/incremental tests (7.75s), core hashes unchanged.
- Ruff check and format check pass.
- [Mandatory PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/44017690441):
  success, 1358 passed (189.72s), clean-database migrations and working-tree checks
  passed on the implementation SHA above. Final CI includes B01 and CLI profiling.
