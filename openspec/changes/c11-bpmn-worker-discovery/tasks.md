# Tasks

All items are intentionally open until code is implemented and tests pass.

- [ ] 1. Review source files, current tests and existing OpenSpec completion receipts; record exact existing behavior.
- [ ] 2. Define identity, provenance, coverage and version fields for the feature; document backward compatibility.
- [ ] 3. Implement: Enumerate D02 source facts and distinguish an actual supported worker handler DECLARATION from a BPMN task referring to a worker key.
- [ ] 4. Implement: Define exact identity keys including engine/profile, worker type or topic, namespace/service when known and source snapshot; preserve missing deployment/activation as PARTIAL.
- [ ] 5. Implement: Extend C02 projector and C04 lookup for worker definitions only; reject incomplete keys as definitive match and retain ambiguity among multiple handlers.
- [ ] 6. Implement: Reuse selected C03 versions, immutable generations, retention pins and C05 cache invalidation; do not insert cross-repository UCM relations.
- [ ] 7. Implement: Add BPMN task in repo A plus worker handler in repo B test and cases of two handlers, config expressions, no worker implementation, unauthorized repo.
- [ ] 8. Test Given/When/Then: Typed definition projection
- [ ] 9. Test Given/When/Then: Reference is not declaration
- [ ] 10. Test Given/When/Then: Ambiguity
- [ ] 11. Test Given/When/Then: No runtime proof
- [ ] 12. Test Given/When/Then: Isolation and versioning
- [ ] 13. Add negative tests for snapshots/versions, missing grants, malformed data, ambiguity, cancellation and rollback.
- [ ] 14. Add PostgreSQL 15 integration fixtures, including reuse/rollback and read API consistency.
- [ ] 15. Run full required PG15 CI and benchmark when relevant; record SHA and evidence in completion.md.
- [ ] 16. Update docs, close tasks only after verified acceptance and then archive the OpenSpec change.
