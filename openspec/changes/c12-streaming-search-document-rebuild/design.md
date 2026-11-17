# Design: Bounded-memory search document generation

## Starting point
C01 search_storage.rebuild_search_documents calls publication.load_snapshot_batch and then materializes document rows. This negates some B02 memory improvements for large repositories, especially in systems with many stored snapshot generations.

## Decisions and integration
### D1
Refactor C01 projection to read published/READY/RETIRED UCM facts in bounded SQL pages and construct document records lazily without whole-snapshot UcmBatch.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D2
Preserve document identity, stable hashes, projection/preprocessing version and the caller-supplied deterministic redaction policy; pass only bounded rows to COPY or bulk stage.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D3
Build a new generation in BUILDING without exposing partial results, and atomically replace the published search generation after integrity/count validation.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D4
Support cancellation, DB failure, invalid redaction policy and concurrent publication/GC with snapshot lease; stale sources cannot replace current generation.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D5
Benchmark 141k and >1M facts: record projection duration, max RSS and document count/hash parity with existing batch projector; reject accidental memory growth.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

## Data lifecycle
Treat UCM snapshots as immutable. Derived discovery/search generations may be rebuilt independently and must remain consistently pinned within one read-only REPEATABLE READ transaction. Selection of other repositories happens only in a trusted version context at query time, not ingestion.

## Security and failure modes
Untrusted source/configuration is never executed. Bounded budgets for memory, candidates and query time. Enforce repository grants before SQL; no source secrets in search projections, diagnostics or logs. On failures the current publication and previous derived generation remain readable.

## Compatibility
Do not break existing C01–C06 API signatures without an explicitly versioned migration and regression tests. Only introduce schema migration if strictly required. Existing migration files are immutable.

## Relevant code
src/code_crawler/search_storage.py; src/code_crawler/search_documents.py; src/code_crawler/publication.py; tests/integration/test_search_document_storage.py; tests/test_search_documents.py; docs/search-documents.md; docs/ucm-publication.md

## Resolved implementation contract

The public C01 rebuild signature and projection version remain unchanged. Root
keyset pages contain at most 128 document-producing entities. Canonical hydration
uses the shared typed `_fetch`/`_parse` path in at most 128-ID pages; only direct
provenance relations (including candidates), SQL accesses/execution owners,
call labels and originating source files are read. `_project_raw` accepts an
internal root-ID selection so contextual entities do not emit extra documents or
invoke caller policy. The unrestricted batch projector remains compatible.

A context is limited to 8,192 entities. Oversized multi-root pages split in ID
order, and an oversized single-root context fails closed. Records and COPY chunks
are bounded to 4 MiB UTF-8. No relation/candidate truncation is permitted. As in
B02, nested payload size of one canonical fact is not an absolute pre-hydration
byte bound. Independent-fact count does not accumulate in Python state.

A private transaction-local staging table accepts bounded COPY pages before
immutable generation metadata/count/security report are inserted. Canonical
schema, existing migration files and generation guard triggers are unchanged.
Final INSERT SELECT, count-checked sealing and generation CAS remain atomic.
Page reports preserve exact counts/category union and first-256 skipped-ID order.
Policy work runs off the event loop, cooperatively stops between documents on
cancellation and is joined before releasing the transaction and snapshot lease.

Authorization precedes DB/policy use. A shared snapshot pin protects the immutable
source from GC. READY/RETIRED offline builds remain supported. After the final
repository lock, both canonical publication and expected search-generation pointer
must still match their original values, otherwise all staged work rolls back.

Regression fixtures exercise all six kinds, tiny pages, complete batch parity,
mask/skip/reject, 260 secret skips, partial-copy failure, cancellation, GC lease,
canonical publication changes, context/copy budgets and a benchmark-owned DB.
