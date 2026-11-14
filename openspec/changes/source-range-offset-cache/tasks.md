# Tasks

- [x] Replace per-range line splitting with a per-file offset index.
- [x] Check line bounds and UTF-8 character boundaries.
- [x] Unit test: scan count independent of range count; negative bounds/UTF-8 cases.
- [x] Benchmark before/after; document in source-adapters.md.
- [x] Unit suite and integration suite pass (integration run on local PostgreSQL 18).
- [ ] Integration suite on PostgreSQL 15 (pending mandatory-postgres-ci).
