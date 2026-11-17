# Design

No new table and no ingestion change: expression GIN indexes over existing fact
tables. `ucm_identifier_words` (immutable SQL) splits identifiers on case changes
and non-alphanumerics. Migration 0019 creates pg_trgm and btree_gin and three GIN
indexes that lead with snapshot_id; the two on ucm_entities are partial over the
five searchable entity types.

`search_text` unions name hits (trigram similarity, substring, word match) with
qualified-name word hits, then ranks EXACT > WORDS > SIMILAR, by trigram similarity,
name and ID. Entity types are validated against a fixed list and inlined as
literals so the planner can prove the partial-index predicate. LIKE wildcards in the
query are escaped. Pagination is limit/offset (offset max 1000) over that
deterministic order, with next_offset in the result.

An explicit snapshot_id is accepted only for a PUBLISHED or RETIRED snapshot of the
named repository. FTS uses the `simple` configuration: identifiers are not prose.
