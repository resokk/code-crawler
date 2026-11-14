# Tasks

- [x] Define typical queries (structural search API).
- [x] Generate a load set and measure EXPLAIN (ANALYZE, BUFFERS) for each query.
- [x] Migration 0018: four B-tree indexes; rewrite three queries to use them.
- [x] Historical PG18 re-measure: no full scans of large tables; record latency baseline and index sizes.
- [x] Check ingest cost with the indexes.
- [x] Unit and integration suites pass (integration run on local PostgreSQL 18).
- [x] Record PG15.20 plans/timings on 141,424 entities, index sizes and committed copy costs; results identical across schema phases.
- [x] Fix selective typed incoming lookup using existing target/candidate indexes; preserve results and paging with a 3,000-filler plan regression.
- [x] Mandatory PostgreSQL 15 suite: 846 passed, no skips; Ruff/format/actionlint pass.
- [ ] Resolve remaining PG15 symbol-hydration scans in simple-name search, execution pages and outward traces.
- [ ] Controlled ingest-overhead and GC measurements: two observed copy samples per phase do not close the bounded-cost requirement.
- [ ] Re-measure on a snapshot above 1M entities once bulk load at that size is practical.
