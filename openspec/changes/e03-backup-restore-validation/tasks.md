# Tasks: Backup and restore of PostgreSQL UCM and source evidence

- [ ] 1. Review current docs and migration/observability or retention implementations; reproduce missing behavior.
- [ ] 2. Define minimal interfaces and durable typed contracts.
- [ ] 3. Implement: Define backup scope and consistency for PostgreSQL 15 public.ucm_*, ingest_*, search_* and resolver_* plus schema migrations.
- [ ] 4. Implement: Automate restore into a fresh isolated PG15 database with reproducible migration/version verification.
- [ ] 5. Implement: Verify published snapshot pointers, source blob SHA, Evidence fragment roundtrip, Relation/FK and retained version contexts.
- [ ] 6. Implement: Rebuild derivative search, embeddings/discovery/resolver cache after restore if needed, without changing canonical facts.
- [ ] 7. Implement: Measure recovery time/backup size and document operator runbook; never use production credentials in tests.
- [ ] 8. Add positive and negative acceptance test: Snapshot backed up with dirty-worktree sources / restoring / exact source evidence fragments match original hashes
- [ ] 9. Add positive and negative acceptance test: Restore lacks derived embedding cache / rebuilding projections / canonical snapshot and reader output remain unchanged
- [ ] 10. Add positive and negative acceptance test: Backup interrupted before consistent point / attempting restore / it fails safely rather than publishing mixed versions
- [ ] 11. Add positive and negative acceptance test: Older pinned snapshot and current snapshot / restore completed / both remain readable and distinguishable
- [ ] 12. Verify snapshot pointer immutability and evidence availability after failure/recovery.
- [ ] 13. Add PostgreSQL 15 integration or operator runbook validation when relevant.
- [ ] 14. Document constraints, security boundaries and explicit Coverage.
- [ ] 15. Run ruff, pytest --require-postgres, CI and failure-injection suite; archive only after all checks pass.
