# Completion: B04 bulk-load FK optimization

Implementation: `d703a379801bc9d877b225793f0e9e07fd327e1b`.
Measured writer SHA256:
`3c81d2085a3e9cc04bacc83841859d18a1a128f541643f8c45c4a1a36870c133`.

Bulk writer transfers each fact slice to canonical storage, truncates/reuses its
temporary staging tables, then ANALYZEs known touched tables in stable order and
flushes all deferred constraints once before commit. Stream input is split at
20k entities; incremental indexing transfers its analysis slices. Transaction
scope, forward/cyclic references, snapshot guards, Evidence, Coverage, certainty
and all PK/FK checks remain intact. No B04 schema/index/collation migration is
needed. The source of the measured fresh-table slowdown was poor FK lookup plans
with empty-table statistics; locale rewrites were not justified by the C/en_US
comparison.

On controlled PG15 20k workloads, fresh full-cycle time changes from 70.378 to
10.906 seconds (C), and 70.329 to 10.849 seconds (en_US.utf8). Warm baseline loads
already benefit from populated statistics; added ANALYZE can cost time, so these
figures are not a universal speedup estimate.

Two completed fresh synthetic workloads of 1,000,001 entities take 762.416 and
719.186 seconds including committed ingest/FK, source archive, semantic validation
and publication, below the preselected 900-second budget. The fresh repeat records
7.16 MiB peak fact staging and exact typed reader sample restoration. The fixture
runs alone on PG15.20, Linux, 2-CPU quota/8 GiB memory, a dedicated 5-GiB tmpfs,
128MB shared buffers and auto plan cache. Parser and production disk throughput
are excluded. Larger single-entity payloads and the linear deferred-trigger queue
remain outside the fact-slice bound; B03 transaction lifetime is unchanged.

The initial disk-backed attempt was cancelled before workspace disk exhaustion.
In tmpfs the first trial completed, then its following trial was cancelled for
capacity; the second acceptance repetition uses a fresh database. First-trial
metrics are preserved as an explicit log-only observation; missing metrics are
not synthesized. CLI now atomically checkpoints verified completed trials with an
explicit incomplete marker, covered by failure/cleanup tests.

Reproducible protocol, detailed provenance and observations:
[query-indexes.md](../../../docs/query-indexes.md#b04-bulk-load-fk-optimization),
[measurement JSON](../../../docs/benchmarks/bulk-pg15-2026-11-16.json).
Measurements use schema through 0029. Main advanced to A03/0030 without changing
the measured writer; full-suite/CI verification includes the A03 index on the
fixture's empty DATABASE_OBJECT table.

Validation:

- A deterministic FK EXPLAIN regression fails on baseline `08d9708` and passes
  with B04, without machine-specific timing assertions.
- Targeted tests cover cyclic/forward references, empty staging between chunks,
  exact full-batch read-back, dangling FK rollback, cancellation/retry, previous
  publication preservation, incremental reuse, locale variants and checkpoint
  persistence after a subsequent failure.
- Ruff check and format check pass.
- Full local mandatory PG15 suite: 1290 passed (324.90s).
- [Mandatory PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/43869595399):
  success, 1290 passed (158.56s), clean-database migrations and working-tree check
  passed on the implementation SHA above.
