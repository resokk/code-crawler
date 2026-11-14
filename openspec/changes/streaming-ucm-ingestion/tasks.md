# Tasks

- [x] Streaming contract and shared staging/transfer steps; batch loader unchanged.
- [x] Integration tests: both orders, five injected faults with retry, memory growth.
- [x] Document in ucm-ingestion.md; unit and integration suites pass (local PostgreSQL 18).
- [x] Measure where indexing memory goes before switching the indexer (docs/ucm-ingestion.md).
- [x] Validation restores a snapshot entity by entity: peak 1855 MB -> 922 MB at 124k entities.
- [ ] Java analyzer catalog keeps all per-file facts (about 0.7 MB per file); switching
      index_incremental to the stream saves nothing until that is fixed.
- [ ] Validate without holding all models (port UcmBatch rules to SQL or streamed checks).
- [ ] Load test at 1M entities; 930k entities did not finish in 50 minutes with the batch loader.
- [ ] Integration suite on PostgreSQL 15.
