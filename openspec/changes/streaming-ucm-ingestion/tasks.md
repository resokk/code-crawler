# Tasks

- [x] Streaming contract and shared staging/transfer steps; batch loader unchanged.
- [x] Integration tests: both orders, five injected faults with retry, memory growth.
- [x] Document in ucm-ingestion.md; unit and integration suites pass (local PostgreSQL 18).
- [x] Measure where indexing memory goes before switching the indexer (docs/ucm-ingestion.md).
- [x] Validation restores a snapshot entity by entity: peak 1855 MB -> 922 MB at 124k entities.
- [x] Java catalog derives occurrences on demand; ORM base cache bounded (output byte-identical).
- [x] index_incremental analyzes in slices, stages as it goes and clones reused facts in SQL:
      indexing peak 653 MB -> 278 MB (first run), 190 MB (incremental) at 124k entities.
- [x] Share equal value objects while restoring: 936k -> 336k model objects, pipeline peak 639 MB.
- [ ] Validate without holding all models (port UcmBatch rules to SQL or streamed checks).
- [ ] Load test at 1M entities; 930k entities did not finish in 50 minutes with the batch loader.
- [x] Integration suite on PostgreSQL 15.

Verified by [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43612670068) at `e8e5f18` (842 tests passed).
