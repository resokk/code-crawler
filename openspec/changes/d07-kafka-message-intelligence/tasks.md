# Tasks: Kafka producers, consumers, topics and schema lineage

- [ ] 1. Review existing UCM, SourceAdapter, symbol resolution and incremental contracts.
- [ ] 2. Define normative typed model, compatibility and detector version.
- [ ] 3. Implement: Extract topic declarations and configuration identities from supported Java Spring Kafka and Kafka client APIs.
- [ ] 4. Implement: Detect producer sends, listener/consumer handlers, serde and message DTO types with local evidence.
- [ ] 5. Implement: Model topic name, cluster/environment context and key/value serialization; preserve dynamic topic expressions as partial.
- [ ] 6. Implement: Create producer/consumer relations to local UCM symbols; use external topic resource selectors for other repositories.
- [ ] 7. Implement: Expose topic/source/handler lookup keys for future discovery; never assume equal topic names mean same cluster.
- [ ] 8. Create positive/negative fixture: Spring KafkaListener with constant topic / indexing / consumer symbol and topic relation include source evidence
- [ ] 9. Create positive/negative fixture: KafkaTemplate send using dynamic topic expression / indexing / topic remains PARTIAL with no fabricated concrete identity
- [ ] 10. Create positive/negative fixture: Identical topic name in two clusters / searching by qualified resource / two resources remain distinct
- [ ] 11. Create positive/negative fixture: Topic consumer in another repository / local indexing / deferred reference is created without cross-repo traversal
- [ ] 12. Test local reference resolving versus deferred cross-repository lookup.
- [ ] 13. Add PostgreSQL 15 integration test from fixture to published UCM with Evidence and SourceAnalysis.
- [ ] 14. Check idempotence and incremental invalidation when adapter fingerprint changes.
- [ ] 15. Update language-specific docs and mark unsupported behavior in Coverage.
- [ ] 16. Run ruff, unit, PG15 integration tests, and review regression results.
