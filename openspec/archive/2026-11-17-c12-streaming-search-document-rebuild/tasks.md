# Tasks

All acceptance scenarios verified; measurements and mandatory PG15 CI are recorded below.

- [x] 1. Review source files, current tests and existing OpenSpec completion receipts; record exact existing behavior.
- [x] 2. Define identity, provenance, coverage and version fields for the feature; document backward compatibility.
- [x] 3. Implement: Refactor C01 projection to read published/READY/RETIRED UCM facts in bounded SQL pages and construct document records lazily without whole-snapshot UcmBatch.
- [x] 4. Implement: Preserve document identity, stable hashes, projection/preprocessing version and the caller-supplied deterministic redaction policy; pass only bounded rows to COPY or bulk stage.
- [x] 5. Implement: Build a new generation in BUILDING without exposing partial results, and atomically replace the published search generation after integrity/count validation.
- [x] 6. Implement: Support cancellation, DB failure, invalid redaction policy and concurrent publication/GC with snapshot lease; stale sources cannot replace current generation.
- [x] 7. Implement: Benchmark 141k and >1M facts: record projection duration, max RSS and document count/hash parity with existing batch projector; reject accidental memory growth.
- [x] 8. Test Given/When/Then: Bounded projection memory
- [x] 9. Test Given/When/Then: Stable equivalence
- [x] 10. Test Given/When/Then: Atomic generation
- [x] 11. Test Given/When/Then: Authorization
- [x] 12. Test Given/When/Then: Concurrent publication
- [x] 13. Test Given/When/Then: Policy change
- [x] 14. Add negative tests for snapshots/versions, missing grants, malformed data, ambiguity, cancellation and rollback.
- [x] 15. Add PostgreSQL 15 integration fixtures, including reuse/rollback and read API consistency.
- [x] 16. Run full required PG15 CI and benchmark when relevant; record SHA and evidence in completion.md.
- [x] 17. Update docs, close tasks only after verified acceptance and then archive the OpenSpec change.

## Initial implementation verification

- Base current main includes completed B02/B03; docs-only audit update `d5aa6c3` integrated.
- Full local mandatory PostgreSQL 15 suite: 1474 passed in 333.56s.
- Final focused projection/security/storage suite: 24 passed in 15.24s, including
  the subsequently added cancellation-worker join check.
- Ruff lint and formatting passed (449 files).
- Small fresh-process benchmark: 31 facts, six documents; all six record fields
  (IDs, type, content, hash, provenance) match batch reference.
- Controlled clean `f5319f3` benchmark: 141,431 and 1,000,011 facts; respectively
  28,286 and 200,002 documents. Both all-record-field hashes match batch reference.
- Batch/stream max RSS: 521.3/91.7 MiB at 141k, 3434.5/94.8 MiB above 1M.
  Stream RSS growth 1.034× for 7.07× facts, below the predeclared 1.5× limit.
- Batch/stream seconds: 63.899/65.497 and 434.329/463.652. Different persistence
  scope is explicit; no isolated speedup or production-disk SLA is claimed.
- The initial CI was superseded by another main push. Required PG15 CI on
  descendant `1616781acb871bd50a5e67a1184b4371b3322a4f`, containing unchanged C12
  implementation, passed: **1489 tests in 330.65s**, clean migrations and tree:
  https://github.com/resokk/code-crawler/actions/runs/44176694371.
- No migrations added/edited. Raw source Evidence, certainty and canonical pointers
  are preserved. Owned benchmark DB cleanup and container shutdown verified.
