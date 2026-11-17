# Proposal: Bounded-memory search document generation

**Priority:** P1

## Problem
C01 search_storage.rebuild_search_documents calls publication.load_snapshot_batch and then materializes document rows. This negates some B02 memory improvements for large repositories, especially in systems with many stored snapshot generations.

## Goal
Refactor C01 projection to read published/READY/RETIRED UCM facts in bounded SQL pages and construct document records lazily without whole-snapshot UcmBatch.

## Scope
- Refactor C01 projection to read published/READY/RETIRED UCM facts in bounded SQL pages and construct document records lazily without whole-snapshot UcmBatch.
- Preserve document identity, stable hashes, projection/preprocessing version and the caller-supplied deterministic redaction policy; pass only bounded rows to COPY or bulk stage.
- Build a new generation in BUILDING without exposing partial results, and atomically replace the published search generation after integrity/count validation.
- Support cancellation, DB failure, invalid redaction policy and concurrent publication/GC with snapshot lease; stale sources cannot replace current generation.
- Benchmark 141k and >1M facts: record projection duration, max RSS and document count/hash parity with existing batch projector; reject accidental memory growth.

## Non-goals
- Do not introduce embeddings or change C01 document semantics in this change.
- Do not rewrite UCM canonical snapshot storage or bypass repository-level authorization.
- Do not assume source documents are secret-free; use trusted redaction before persistence.

## Dependencies
C01 and B02; A06 policy before generating embeddings.

## Touched files
src/code_crawler/search_storage.py; src/code_crawler/search_documents.py; src/code_crawler/publication.py; tests/integration/test_search_document_storage.py; tests/test_search_documents.py; docs/search-documents.md; docs/ucm-publication.md

## Risks
- Inferred name matches must not become definite runtime dependencies.
- New storage data must be versioned and derived from immutable published UCM; do not reindex other repositories.
- Failed generation or resolver request must never alter a previously published snapshot or visible generation.
