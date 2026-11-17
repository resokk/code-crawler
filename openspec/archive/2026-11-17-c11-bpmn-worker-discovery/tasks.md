# Tasks

All acceptance checks are complete; see completion.md for the implementation SHA and required PostgreSQL 15 CI evidence.

- [x] 1. Review source files, current tests and existing OpenSpec completion receipts; record exact existing behavior.
- [x] 2. Define identity, provenance, coverage and version fields for the feature; document backward compatibility.
- [x] 3. Implement: Enumerate D02 source facts and distinguish an actual supported worker handler DECLARATION from a BPMN task referring to a worker key.
- [x] 4. Implement: Define exact identity keys including engine/profile, worker type or topic, namespace/service when known and source snapshot; preserve missing deployment/activation as PARTIAL.
- [x] 5. Implement: Extend C02 projector and C04 lookup for worker definitions only; reject incomplete keys as definitive match and retain ambiguity among multiple handlers.
- [x] 6. Implement: Reuse selected C03 versions, immutable generations, retention pins and C05 cache invalidation; do not insert cross-repository UCM relations.
- [x] 7. Implement: Add BPMN task in repo A plus worker handler in repo B test and cases of two handlers, config expressions, no worker implementation, unauthorized repo.
- [x] 8. Test Given/When/Then: Typed definition projection
- [x] 9. Test Given/When/Then: Reference is not declaration
- [x] 10. Test Given/When/Then: Ambiguity
- [x] 11. Test Given/When/Then: No runtime proof
- [x] 12. Test Given/When/Then: Isolation and versioning
- [x] 13. Add negative tests for snapshots/versions, missing grants, malformed data, ambiguity, cancellation and rollback.
- [x] 14. Add PostgreSQL 15 integration fixtures, including reuse/rollback and read API consistency.
- [x] 15. Run full required PG15 CI and benchmark when relevant; record SHA and evidence in completion.md.
- [x] 16. Update docs, close tasks only after verified acceptance and then archive the OpenSpec change.
