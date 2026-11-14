# UCM query index optimization

Structural search queries were written before any plan was measured. Define the
typical queries, measure them with EXPLAIN (ANALYZE, BUFFERS) on a load set, add
the indexes that remove full scans of large fact tables, check their ingest cost
and record a latency and index size baseline. No change to query results.
