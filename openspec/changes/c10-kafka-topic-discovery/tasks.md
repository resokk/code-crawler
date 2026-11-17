# Tasks

Implementation and targeted PostgreSQL 15 checks are complete. Full-suite CI and archival receipts remain open.

- [x] 1. Review source files, current tests and existing OpenSpec completion receipts; record exact existing behavior.
- [x] 2. Define identity, provenance, coverage and version fields for the feature; document backward compatibility.
- [x] 3. Implement: Inspect D07 UCM facts and define a strict predicate for a Kafka topic DECLARATION; exclude mere KafkaTemplate.send, listener subscriptions, dynamic expressions and client configurations from confirmed definitions.
- [x] 4. Implement: Extend repository-local discovery projection to project only supported typed declarations, with source UCM entity ID, snapshot/generation, exact topic key, optional cluster/namespace/environment and Evidence.
- [x] 5. Implement: Expose KAFKA_TOPIC exact lookup and selector normalization through existing C02/C04, with bounded fanout, authorization, explicit PARTIAL coverage and no confirmed runtime delivery edges.
- [x] 6. Implement: Version the discovery projector and support deterministic refresh, old-pinned generation reads and cache miss on updated generations without cross-repo ingest.
- [x] 7. Implement: Add synthetic multi-repository fixture and negative cases: same topic in two clusters, subscription without definition, dynamic topic, ambiguous names, missing generation.
- [x] 8. Test Given/When/Then: Producer declaration only
- [x] 9. Test Given/When/Then: Unknown cluster context
- [x] 10. Test Given/When/Then: Dynamic topic
- [x] 11. Test Given/When/Then: Versioned freshness
- [x] 12. Test Given/When/Then: Security
- [x] 13. Add negative tests for snapshots/versions, missing grants, malformed data, ambiguity, cancellation and rollback.
- [x] 14. Add PostgreSQL 15 integration fixtures, including reuse/rollback and read API consistency.
- [ ] 15. Run full required PG15 CI and benchmark when relevant; record SHA and evidence in completion.md.
- [ ] 16. Update docs, close tasks only after verified acceptance and then archive the OpenSpec change.
