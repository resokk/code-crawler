# Tasks: Pinned snapshot retention and derived data lifecycle

- [ ] 1. Review current docs and migration/observability or retention implementations; reproduce missing behavior.
- [ ] 2. Define minimal interfaces and durable typed contracts.
- [ ] 3. Implement: Define retention classes CURRENT, RETIRED, PINNED, BUILDING/FAILED and minimum preservation periods/explicit pins.
- [ ] 4. Implement: Introduce durable pin references for selected snapshot IDs, explicit owner/use and release/audit workflow.
- [ ] 5. Implement: Make GC mark/sweep across UCM facts, source blobs, search docs, embeddings, discovery and resolver generations without deleting live dependencies.
- [ ] 6. Implement: Support dry-run with planned bytes/entities and safe transaction/retry; no destructive unspecified defaults.
- [ ] 7. Implement: Document rollback after publication and behavior when old snapshots are intentionally expired.
- [ ] 8. Add positive and negative acceptance test: Retired snapshot pinned by deployment context / running GC / pinned snapshot and evidence remain intact
- [ ] 9. Add positive and negative acceptance test: Two snapshots share source blob / deleting one snapshot / shared blob remains available to the other
- [ ] 10. Add positive and negative acceptance test: Snapshot has no live references / retention expires / facts and only truly orphan derived resources are removed
- [ ] 11. Add positive and negative acceptance test: GC preview invoked / printing plan / nothing is deleted until explicit approval/execution
- [ ] 12. Verify snapshot pointer immutability and evidence availability after failure/recovery.
- [ ] 13. Add PostgreSQL 15 integration or operator runbook validation when relevant.
- [ ] 14. Document constraints, security boundaries and explicit Coverage.
- [ ] 15. Run ruff, pytest --require-postgres, CI and failure-injection suite; archive only after all checks pass.
