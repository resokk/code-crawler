# Tasks

- [x] Define typical queries (structural search API).
- [x] Generate a load set and measure EXPLAIN (ANALYZE, BUFFERS) for each query.
- [x] Migration 0018: four B-tree indexes; rewrite three queries to use them.
- [x] Re-measure: no full scans of large tables; record latency baseline and index sizes.
- [x] Check ingest cost with the indexes.
- [x] Unit and integration suites pass (integration run on local PostgreSQL 18).
- [ ] Confirm plans and timings on PostgreSQL 15.
- [ ] Re-measure on a snapshot above 1M entities once bulk load at that size is practical.
