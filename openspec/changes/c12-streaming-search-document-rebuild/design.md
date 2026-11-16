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
