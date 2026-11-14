# Design

`code_crawler.search` holds async functions over an asyncpg connection. Each
resolves the repository's publication pointer once and queries that immutable
snapshot with plain SQL; traversal is one recursive CTE bounded by depth (max 6).

Every query fetches limit+1 rows (limit max 200) and reports `truncated`.
Relation results are enriched in batches: endpoints, evidence, coverage reasons
and candidates are fetched with `= ANY(ids)` rather than per row.

Nothing is inferred at query time. Unresolved and ambiguous relations are returned
with resolution, reason and candidates; callers also match relation candidates.
Traversal follows RESOLVED relations only. An execution without statements and a
data access without executions are returned as such.

Name matching is exact; table/column names match the stored normalized name or
its lowercase form. No migration: indexes are a separate change.
