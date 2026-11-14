# Tasks

- [x] Document job state, retry and GC contract (docs/ingest-jobs.md).
- [x] Migration 0016: ingest_jobs and GC-scoped guard exceptions for RETIRED.
- [x] Record jobs from index-sources; structured failure diagnostics.
- [x] `jobs list`, `jobs retry`, `snapshot gc`.
- [x] Integration tests: failure diagnostics, retry, lock refusal, reap, BUILDING cleanup, retention, guard without flag.
- [x] Unit and integration suites pass (integration run on local PostgreSQL 18).
- [ ] Integration suite on PostgreSQL 15 (pending mandatory-postgres-ci).
- [ ] GC timing on a large snapshot.
