# Tasks

- [x] Streaming contract and shared staging/transfer steps; batch loader unchanged.
- [x] Integration tests: both orders, five injected faults with retry, memory growth.
- [x] Document in ucm-ingestion.md; unit and integration suites pass (local PostgreSQL 18).
- [ ] Switch index_incremental to the stream and validate without loading the snapshot.
- [ ] Load test at 1M entities; 930k entities did not finish in 50 minutes with the batch loader.
- [ ] Integration suite on PostgreSQL 15.
