# Capability: kafka-message-intelligence

## ADDED Requirements

### Requirement: Extract topic declarations and configuration identities from supported Java Spring Kafka and Kafka client APIs.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Spring KafkaListener with constant topic
- GIVEN Spring KafkaListener with constant topic
- WHEN indexing
- THEN consumer symbol and topic relation include source evidence

### Requirement: Detect producer sends, listener/consumer handlers, serde and message DTO types with local evidence.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: KafkaTemplate send using dynamic topic expression
- GIVEN KafkaTemplate send using dynamic topic expression
- WHEN indexing
- THEN topic remains PARTIAL with no fabricated concrete identity

### Requirement: Model topic name, cluster/environment context and key/value serialization; preserve dynamic topic expressions as partial.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Identical topic name in two clusters
- GIVEN Identical topic name in two clusters
- WHEN searching by qualified resource
- THEN two resources remain distinct

### Requirement: Create producer/consumer relations to local UCM symbols; use external topic resource selectors for other repositories.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Topic consumer in another repository
- GIVEN Topic consumer in another repository
- WHEN local indexing
- THEN deferred reference is created without cross-repo traversal

### Requirement: Local indexing and transparent coverage
Every adapter MUST be independent of external repository availability and MUST emit evidence for inferred local links and deferred selectors for remote targets.

#### Scenario: Remote target missing
- GIVEN source code references a symbol, endpoint or resource in an unavailable other repository
- WHEN the current repository is indexed
- THEN publishing can complete without a guessed cross-repository relation, and ExternalReference remains discoverable
