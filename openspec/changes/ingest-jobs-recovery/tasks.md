# Tasks

- [x] Document job state, retry and GC contract (docs/ingest-jobs.md).
- [x] Migration 0016: ingest_jobs and GC-scoped guard exceptions for RETIRED.
- [x] Record jobs from index-sources; structured failure diagnostics.
- [x] `jobs list`, `jobs retry`, `snapshot gc`.
- [x] Integration tests: failure diagnostics, retry, lock refusal, reap, BUILDING cleanup, retention, guard without flag.
- [x] Unit and integration suites pass (integration run on local PostgreSQL 18).
- [x] Integration suite on PostgreSQL 15.
- [x] P0: restrict GC to an explicit snapshot-table registry; foreign UUID/text tables remain intact; migrated-schema registry coverage and mandatory PG15 suite pass (849 tests).
- [x] GC timing on a large snapshot: 121-124 s for 141,424 entities on PG15 (load takes 25 s); cause and limits
      in docs/ingest-jobs.md. Not run above 1M entities; speeding GC up is change b06.

Verified by [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43612670068) at `e8e5f18` (842 tests passed).
