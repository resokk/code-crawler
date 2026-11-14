# Tasks

- [x] Streaming contract and shared staging/transfer steps; batch loader unchanged.
- [x] Integration tests: both orders, five injected faults with retry, memory growth.
- [x] Document in ucm-ingestion.md; unit and integration suites pass (local PostgreSQL 18).
- [x] Measure where indexing memory goes before switching the indexer (docs/ucm-ingestion.md).
- [x] Validation restores a snapshot entity by entity: peak 1855 MB -> 922 MB at 124k entities.
- [ ] Re-measure retained Java catalog/cache memory after on-demand occurrences
      (`50a71ca`) and the bounded ORM base cache (`be53229`); use the result to
      choose the next step before switching index_incremental to streaming.
- [ ] Validate without holding all models (port UcmBatch rules to SQL or streamed checks).
- [ ] Load test at 1M entities; 930k entities did not finish in 50 minutes with the batch loader.
- [x] Integration suite on PostgreSQL 15.

Verified by [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43612670068) at `e8e5f18` (842 tests passed).
