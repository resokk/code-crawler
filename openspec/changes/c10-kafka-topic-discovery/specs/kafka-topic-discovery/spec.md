# Capability: kafka-topic-discovery

## ADDED Requirements

### Requirement: Producer declaration only
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Producer declaration only
- GIVEN A Java module explicitly declares a NewTopic resource with a static topic and supported configuration
- WHEN the repository is published and discovery projected
- THEN a KAFKA_TOPIC entry is available with typed declaration entity and Evidence, while another module that only calls KafkaTemplate.send does not create a target declaration

### Requirement: Unknown cluster context
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Unknown cluster context
- GIVEN Two repos declare topic payments without confirmed cluster identity
- WHEN global lookup runs
- THEN both remain candidate identities with PARTIAL/AMBIGUOUS status; no auto-RESOLVED physical topic

### Requirement: Dynamic topic
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Dynamic topic
- GIVEN Kafka topic name is built from a runtime property
- WHEN D07 and discovery run
- THEN no fabricated static topic lookup key is published and SourceAnalysis records incomplete coverage

### Requirement: Versioned freshness
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Versioned freshness
- GIVEN A topic declaration is renamed on a newer published snapshot
- WHEN C02 refresh and C04 query are repeated
- THEN only the selected version's declaration is considered; stale cache/generation does not return a confirmed old target

### Requirement: Security
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Security
- GIVEN Caller can access repo A but not B
- WHEN searching KAFKA_TOPIC
- THEN repo B declaration metadata and Evidence are not disclosed

### Requirement: No false confirmed relationship
A declaration key or semantic similarity alone MUST NOT be treated as proof that an external runtime call executed.

#### Scenario: Partial source coverage
- GIVEN source/framework identity or runtime environment is incomplete
- WHEN discovery or projection executes
- THEN coverage is PARTIAL or UNSUPPORTED, and no new STATIC_PROVEN runtime edge is manufactured
