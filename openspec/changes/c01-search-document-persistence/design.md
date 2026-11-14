# Design: Хранение версионированных поисковых документов

## Context
Существует search_documents.project(), но документы не сохраняются и не участвуют в published-generation lifecycle.

## Proposed design
### Decision 1
Создать search_documents и search_index_generations с (repository,snapshot,generation,entity_id,document_type,content,hash,provenance).

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 2
Обеспечить deterministic projection: одинаковые UCM facts + версия генератора дают одинаковые hashes и doc identity.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 3
Публиковать generation атомарно и не показывать incomplete batches; поддержать reindex search без изменения UCM snapshot.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

### Decision 4
Разделить target-language/summary и redacted source; учитывать secret policy и ACL по repository.

Implementation follows existing UCM entity, immutable snapshot, Evidence and read-only MCP contracts. For any inferred link, return separate certainty, resolution and coverage; do not conflate candidate discovery with proof.

## Consistency and lifecycle
- Canonical UCM snapshots are immutable. Derived search documents, catalogs, embeddings and resolver caches carry snapshot/generation keys.
- Indexing one repository MUST NOT depend on another; remote references are resolved only at query-time.
- Published readers MUST see one coherent generation across one query or report explicit partial availability.
- No unauthorised access to repository source/evidence; default fail closed when auth is needed.

## Risks and recovery
Avoid unbounded search/fanout, wrong version selection and leakage of secrets via embeddings. A failed derivative generation leaves the previous published generation available. Forward migrations and PG15 tests are required for schema changes.

## Interfaces affected
src/code_crawler/search_documents.py; src/code_crawler/migrations/; src/code_crawler/publication.py; tests/integration/; docs/search-documents.md

## Dependencies
A06 желательно; B02

## Resolved implementation contract

- Migration 0021 adds `search_index_generations`, `search_documents` and the
  per-(repository,snapshot) `search_index_publications` pointer. Composite FKs
  constrain both provenance and generation ownership. A sealed generation has a
  checked document count and immutable documents/metadata.
- The reproducible fixture starts with a published UCM snapshot but no search
  generation: read raises LookupError. Rebuild produces stable document IDs and
  SHA-256 of canonical content JSON; rebuilding changes only generation identity.
  The fixture covers symbol, SQL, ORM and incremental reuse.
- `search_storage.rebuild_search_documents` performs projection, COPY, seal and
  expected-generation CAS in one transaction. It never changes canonical facts
  or canonical publication. Errors/cancellation roll back the entire generation.
  No persisted BUILDING search generation or resumable batch protocol is needed
  for this scope; the previous sealed generation remains visible throughout.
- `read_search_documents` selects canonical publication and search generation in
  one statement. Missing search availability raises LookupError. Explicit old
  snapshots cannot bypass publication selection. Keyset pagination is bounded;
  compound reads use read-only REPEATABLE READ.
- Mandatory allowed_repository_ids is supplied by trusted authorization code,
  never a client-chosen MCP parameter. A deterministic caller-provided redactor
  and policy_version are mandatory. Source text is separated from summary and
  redacted before persistence; reasons and Evidence descriptions use the policy
  too. This is the integration boundary for A02/A06, not their implementation.
- Existing project() callers retain their text hash and document IDs. Persisted
  content has its own JSON hash. ORM_MAPPING/ORM_QUERY are additive document types.
  Source entity IDs, snapshot/generation, Relation resolution/certainty/Evidence/
  Coverage remain available; no similarity-based dependencies are constructed.
- GC explicitly registers the derivative tables and deletes generations before
  canonical facts, cascading sealed documents. Published generations of other
  snapshots/repositories remain unaffected.

B02 remains unfinished: this implementation reuses the full-snapshot loader and
projector and makes no bounded-memory or scale claim. Functional persistence can
be verified independently; B02/B03 and generation retention remain separate work.
Full API, version/hash and compatibility details are in docs/search-documents.md.
