# Design

The typical queries are the eight structural search functions. On a 124k-entity
snapshot four of them scanned a whole fact table. Migration 0018 adds four B-tree
indexes, each tied to one measured scan; three queries are rewritten so the planner
can use them (UNION ALL of IDs instead of OR across tables, JOIN instead of EXISTS
on the table name).

No separate relation_kind or access_kind index: existing relation indexes already
end in relation_kind, and access_kind is a low-selectivity filter applied after the
name lookup. No GIN: every predicate is an equality. No index without a query.

Baseline, sizes and ingest cost are recorded in docs/query-indexes.md. The original
measurements used local PostgreSQL 18. The follow-up records PostgreSQL 15.20
results separately, including remaining symbol-hydration scans and unresolved
controlled-load and >1M-entity acceptance items.

The PG15 follow-up uses an opt-in isolated-database harness with generated JDBC
sources, including ambiguous call targets. It captures actual search and typed
reader SQL, warm API latency and EXPLAIN ANALYZE BUFFERS separately. Two committed
batch copies per schema phase report loader cost independently of parsing.
Historical PG18 numbers remain separately labelled; they are not a cross-machine
speed comparison.

Typed incoming lookup repeats the earlier OR/EXISTS pitfall: one incoming CALLS
result filtered 74,403 other relations in a 141,424-entity snapshot. Use the existing
target/candidate indexes through an ID union and a membership predicate, preserving
deduplication and all reader semantics without a schema migration. A selective
3,000-filler integration fixture checks the plan without disabling sequential scans
or imposing timing thresholds.

Symbol hydration: for a page of keys PG15 hash-joined the whole of `ucm_symbols`,
a few thousand rows per snapshot. The three joins become LATERAL subqueries ending
in OFFSET 0, which the planner cannot flatten, so each key goes through the primary
key. No index is added. A 3,000-symbol integration fixture checks the plan.

The harness takes `--copies N`: N committed copy + GC trials per schema phase, 0 to
skip them. The controlled run uses three on an idle server; the run above 1M
entities uses none, since GC of one copy at that size takes hours.
