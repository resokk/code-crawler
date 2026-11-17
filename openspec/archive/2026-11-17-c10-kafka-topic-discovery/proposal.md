# Proposal: Kafka topic declaration discovery

**Priority:** P1

## Problem
D07 now extracts typed Kafka topic resources and producers/consumers, but discovery._SUPPORTED still declares KAFKA_TOPIC UNSUPPORTED. Query-time Kafka ExternalReference cannot find declaration candidates even when D07 has a legitimate local definition.

## Goal
Inspect D07 UCM facts and define a strict predicate for a Kafka topic DECLARATION; exclude mere KafkaTemplate.send, listener subscriptions, dynamic expressions and client configurations from confirmed definitions.

## Scope
- Inspect D07 UCM facts and define a strict predicate for a Kafka topic DECLARATION; exclude mere KafkaTemplate.send, listener subscriptions, dynamic expressions and client configurations from confirmed definitions.
- Extend repository-local discovery projection to project only supported typed declarations, with source UCM entity ID, snapshot/generation, exact topic key, optional cluster/namespace/environment and Evidence.
- Expose KAFKA_TOPIC exact lookup and selector normalization through existing C02/C04, with bounded fanout, authorization, explicit PARTIAL coverage and no confirmed runtime delivery edges.
- Version the discovery projector and support deterministic refresh, old-pinned generation reads and cache miss on updated generations without cross-repo ingest.
- Add synthetic multi-repository fixture and negative cases: same topic in two clusters, subscription without definition, dynamic topic, ambiguous names, missing generation.

## Non-goals
- Do not infer deployment/physical Kafka cluster from a topic string or Spring annotation alone.
- Do not assert that producer has sent or consumer has received messages at runtime.
- Do not index other repositories from D07 or mutate canonical relations.

## Dependencies
C02, C04 and D07 already implemented; optionally A02 before exposing global MCP.

## Touched files
src/code_crawler/discovery.py; src/code_crawler/external_candidates.py; src/code_crawler/kafka_adapter.py; src/code_crawler/kafka_java.py; tests/test_discovery_search.py; tests/integration/test_discovery_catalog_extended.py; docs/global-discovery-catalog.md; docs/external-reference-candidates.md

## Risks
- Inferred name matches must not become definite runtime dependencies.
- New storage data must be versioned and derived from immutable published UCM; do not reindex other repositories.
- Failed generation or resolver request must never alter a previously published snapshot or visible generation.
