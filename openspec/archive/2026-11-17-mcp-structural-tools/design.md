# Design

`server.py` registers search_symbols, find_callers, find_callees,
find_sql_executions, find_table_readers, find_table_writers, trace_dependency and
get_evidence. Each validates arguments through its typed signature (entity ID
pattern, limit 1..200, depth 1..6), acquires a pooled connection, opens a
read-only transaction and delegates to the matching `code_crawler.search` function.

The asyncpg pool is created once in the server lifespan from DATABASE_URL, per
the "load once at start" rule; no per-request or cross-request state is kept, so
stateless HTTP holds. ValueError from the search layer becomes a ToolError with
the same message. Results are returned unchanged, so uncertainty fields
(truncated, resolution, coverage, empty statements/executions) reach the agent.
