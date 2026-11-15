# Tasks: Kafka producers, consumers, topics and schema lineage

- [x] 1. Review existing UCM, SourceAdapter, symbol resolution and incremental contracts.
- [x] 2. Define normative typed model, compatibility and detector version.
- [x] 3. Implement: Extract topic declarations and configuration identities from supported Java Spring Kafka and Kafka client APIs.
- [x] 4. Implement: Detect producer sends, listener/consumer handlers, serde and message DTO types with local evidence.
- [x] 5. Implement: Model topic name, cluster/environment context and key/value serialization; preserve dynamic topic expressions as partial.
- [x] 6. Implement: Create producer/consumer relations to local UCM symbols; use external topic resource selectors for other repositories.
- [x] 7. Implement: Expose topic/source/handler lookup keys for future discovery; never assume equal topic names mean same cluster.
- [x] 8. Create positive/negative fixture: Spring KafkaListener with constant topic / indexing / consumer symbol and topic relation include source evidence
- [x] 9. Create positive/negative fixture: KafkaTemplate send using dynamic topic expression / indexing / topic remains PARTIAL with no fabricated concrete identity
- [x] 10. Create positive/negative fixture: Identical topic name in two clusters / searching by qualified resource / two resources remain distinct
- [x] 11. Create positive/negative fixture: Topic consumer in another repository / local indexing / deferred reference is created without cross-repo traversal
- [x] 12. Test local reference resolving versus deferred cross-repository lookup.
- [x] 13. Add PostgreSQL 15 integration test from fixture to published UCM with Evidence and SourceAnalysis.
- [x] 14. Check idempotence and incremental invalidation when adapter fingerprint changes.
- [x] 15. Update language-specific docs and mark unsupported behavior in Coverage.
- [ ] 16. Run ruff, unit, PG15 integration tests, and review regression results.


## Acceptance evidence

Local PostgreSQL 15 (Docker postgres:15), 2026-11-15, after integrating current GC
and bounded snapshot validation work:
`uv run ruff check .`, `uv run ruff format --check .`,
`uv run pytest --require-postgres -x -q`: **1171 passed in 219.09s**.

Focused Kafka unit/storage suite: 28 passed. Kafka plus mixed VBScript compatibility
suite: 29 passed. Tests cover Spring/Apache APIs, explicit cluster separation,
source-only environment/config candidates, DTO/serde local/ambiguous/missing/generic
resolution, dynamic/invalid topic names, map snapshots/branch/escape/assignment,
configuration errors/ambiguity, budgets/cyclic constants, shared AST/BPMN catalogs,
PG15 migration, archived Evidence, full/incremental equality, unchanged reuse,
analyzer upgrade, config edits, consumer removal, repository isolation and failed
producer publication preservation. The VBScript fixture now mirrors the active
CLI Java wrapper and keeps the no-reanalysis assertion.

Migration: 0027_kafka_message_intelligence.sql. No new storage graph or dependency.
Coverage remains PARTIAL and source-candidate status is explicit. No runtime Kafka,
Spring bean/deployment or cross-repository delivery proof is claimed. Global Kafka
discovery/resolver integration is deferred; qualified local resource lookup passes.
The complete contract and limitations are in docs/kafka-message-intelligence.md.
Mandatory GitHub CI is recorded after the implementation run.
