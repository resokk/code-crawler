# Design

The typical queries are the eight structural search functions. On a 124k-entity
snapshot four of them scanned a whole fact table. Migration 0018 adds four B-tree
indexes, each tied to one measured scan; three queries are rewritten so the planner
can use them (UNION ALL of IDs instead of OR across tables, JOIN instead of EXISTS
on the table name).

No separate relation_kind or access_kind index: existing relation indexes already
end in relation_kind, and access_kind is a low-selectivity filter applied after the
name lookup. No GIN: every predicate is an equality. No index without a query.

Baseline, sizes and ingest cost are recorded in docs/query-indexes.md. Measured on
local PostgreSQL 18; PostgreSQL 15 confirmation is an open task.
