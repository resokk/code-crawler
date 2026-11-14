# Tasks

- [x] Record Git listing and stat signatures in the captured inventory.
- [x] Accept the inventory in index_incremental; pass it from all index entry points.
- [x] Replace the final re-capture with stat-based verification and selective re-read.
- [x] Unit test: no re-read when unchanged, selective re-read, change and delete detected.
- [x] Document in ucm-incremental.md; unit and integration suites pass (local PostgreSQL 18).
- [ ] Integration suite on PostgreSQL 15 (pending mandatory-postgres-ci).
