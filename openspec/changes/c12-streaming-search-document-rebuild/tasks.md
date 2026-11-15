# Tasks

All items are intentionally open until code is implemented and tests pass.

- [ ] 1. Review source files, current tests and existing OpenSpec completion receipts; record exact existing behavior.
- [ ] 2. Define identity, provenance, coverage and version fields for the feature; document backward compatibility.
- [ ] 3. Implement: Refactor C01 projection to read published/READY/RETIRED UCM facts in bounded SQL pages and construct document records lazily without whole-snapshot UcmBatch.
- [ ] 4. Implement: Preserve document identity, stable hashes, projection/preprocessing version and the caller-supplied deterministic redaction policy; pass only bounded rows to COPY or bulk stage.
- [ ] 5. Implement: Build a new generation in BUILDING without exposing partial results, and atomically replace the published search generation after integrity/count validation.
- [ ] 6. Implement: Support cancellation, DB failure, invalid redaction policy and concurrent publication/GC with snapshot lease; stale sources cannot replace current generation.
- [ ] 7. Implement: Benchmark 141k and >1M facts: record projection duration, max RSS and document count/hash parity with existing batch projector; reject accidental memory growth.
- [ ] 8. Test Given/When/Then: Bounded projection memory
- [ ] 9. Test Given/When/Then: Stable equivalence
- [ ] 10. Test Given/When/Then: Atomic generation
- [ ] 11. Test Given/When/Then: Authorization
- [ ] 12. Test Given/When/Then: Concurrent publication
- [ ] 13. Test Given/When/Then: Policy change
- [ ] 14. Add negative tests for snapshots/versions, missing grants, malformed data, ambiguity, cancellation and rollback.
- [ ] 15. Add PostgreSQL 15 integration fixtures, including reuse/rollback and read API consistency.
- [ ] 16. Run full required PG15 CI and benchmark when relevant; record SHA and evidence in completion.md.
- [ ] 17. Update docs, close tasks only after verified acceptance and then archive the OpenSpec change.
