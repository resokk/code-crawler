# Completion: C12 bounded search document rebuild

Implementation and measured clean SHA:
`f5319f3ccd3e69b48be8f5a77d1646e2198debc8`.
Required CI acceptance SHA (contains the unchanged C12 implementation):
`1616781acb871bd50a5e67a1184b4371b3322a4f`.

C01 storage rebuild now hydrates bounded canonical neighborhoods instead of
loading a whole UcmBatch. Root/hydration pages are at most 128 IDs; context is
limited to 8,192 facts with adaptive root-page splitting. A single oversized
context or record fails closed. COPY chunks/records are bounded to 4 MiB UTF-8.
Independent-fact count does not accumulate in the Python catalog or document list.
A single canonical nested payload remains outside an absolute pre-hydration byte
bound, as documented for B02. The unrestricted pure batch formatter is retained.

A private temporary stage preserves the existing immutable generation metadata
contract: counts and aggregate security report are final before creating the
unsealed generation. Insert, count-checked seal and CAS publication remain atomic.
Authorization precedes source/policy calls. Snapshot lease protects concurrent GC;
canonical publication and expected generation are rechecked under the final repo
lock. Cancellation joins policy work before releasing the lease/transaction.
READY/RETIRED offline builds, version strings, hashes and reader API remain valid.
No migration, durable table, raw source or canonical certainty/evidence is changed.

Acceptance:

- All six document types match batch content, IDs, hashes and full provenance.
  Tiny-page, mask/skip/reject, 260-skip diagnostics and first-256-ID order pass.
- Partial staging SQL failure, cancellation, policy/structural failures, context
  and byte budgets preserve the previous complete generation. No facts are
  silently truncated; ambiguous/unresolved statuses remain original.
- Concurrent canonical publication rejects stale swap; GC skips the pinned source
  and can collect it after release. Denied access precedes DB/policy invocation.
  Existing full/incremental rebuild, concurrent CAS and pinned pagination pass.
- Fixed-degree synthetic ring/candidate benchmark uses owned PG15 DBs and fresh
  batch/stream processes. At 141,431 facts, both modes produce 28,286 documents;
  RSS 521.3 MiB batch versus 91.7 MiB stream, seconds 63.899 versus 65.497.
- At **1,000,011 facts**, both produce **200,002 documents** with identical full
  six-field record SHA256, including provenance. RSS **3434.5 MiB versus 94.8 MiB**;
  seconds 434.329 versus 463.652. The large canonical count was independently
  checked with SQL. Stream RSS growth **1.034×** for **7.07×** facts passes the
  predeclared <1.5× memory-growth criterion.
- All owned databases were removed; the benchmark-only PG15 container was stopped.

[Benchmark and host/IO metadata](../../../docs/benchmarks/search-projection-pg15.json)
and [contract/reproduction](../../../docs/search-documents.md).
PGDATA was tmpfs 3 GiB; host quota 2 CPUs/8 GiB. Docker's requested 4-GiB limit is
not treated as isolated because the observed cgroup reports the shared 8-GiB cap.
RSS is conservative resource.ru_maxrss, possibly retaining startup/pre-exec peak.
Stream timing includes persisted stage/seal/swap; batch timing excludes writing.
These are memory/parity observations, not a speedup or production-disk SLO.

Verification:

- Full local mandatory PG15 suite: 1474 passed in 333.56s.
- Final focused projection/security suite: 24 passed in 15.24s, including the
  additional cancellation-worker join regression.
- Ruff lint/format passed; final descendant-main checks passed (459 files).
- [Required PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/44176694371)
  on acceptance SHA above: **1489 passed in 330.65s**, clean migrations and
  working-tree checks passed. The initial implementation run was automatically
  superseded by that descendant main push, not a test failure.
