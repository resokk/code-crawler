# Tasks: A07 migration history and schema resolution

Do not check off tasks without real PostgreSQL 15 and historical-upgrade evidence.

## Phase 1 — prove/characterize the risk
- [ ] 1. Pin historical sources at `b5b3f35`, create populated PG15 fixtures and record schema/reader/Evidence before upgrade.
- [ ] 2. Run `main@e133ccc` migration/reader on the historical fixture; record actual drift/failures and verify old snapshot preservation.
- [ ] 3. Test clean install vs historical upgrade and non-default search_path with intentionally colliding schemas.
- [ ] 4. Test both 0030 files in fresh and existing migration histories; define ordering acceptance.

## Phase 2 — implement future integrity guarantees
- [ ] 5. Select schema policy (fixed public or configured explicit schema) and document supported connection behavior.
- [ ] 6. Add checksum and provenance-aware migration metadata using a forward-only upgrade path.
- [ ] 7. Implement checksum mismatch fail-closed in `db status/db migrate`; keep legacy provenance explicitly UNVERIFIED pending reconciliation.
- [ ] 8. Implement guarded `search_path`/qualified identifier handling for migration metadata, DDL and runtime UCM queries.
- [ ] 9. Define a non-destructive operator remediation/approved provenance process; never silently overwrite historical hashes.

## Phase 3 — regression/CI/acceptance
- [ ] 10. Add PG15 tests covering historical→current upgrade with nonempty snapshots, search, source blobs and retained contexts.
- [ ] 11. Add negative tests: altered historical migration content, wrong schema, colliding schema_migrations, unknown provenance, late 0030 ordering.
- [ ] 12. Verify migration rollback/atomicity on DDL failure; previously published snapshot remains unchanged.
- [ ] 13. Update `docs/db.md`, CI upgrade job and release notes with exact operator steps.
- [ ] 14. Run Ruff, format, full `pytest --require-postgres` and hosted PG15 CI; keep reported fixtures and hashes.
- [ ] 15. Archive OpenSpec with completion receipt only once every Given/When/Then scenario passes.
