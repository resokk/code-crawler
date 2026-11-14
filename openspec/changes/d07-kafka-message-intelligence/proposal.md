# Proposal: Kafka producers, consumers, topics and schema lineage

## Why
Kafka dependencies are not represented as local UCM graph or discovery entries.

## Goal
Implement Kafka producers, consumers, topics and schema lineage as a dedicated, versioned SourceAdapter producing canonical UCM facts.

## Scope
- Extract topic declarations and configuration identities from supported Java Spring Kafka and Kafka client APIs.
- Detect producer sends, listener/consumer handlers, serde and message DTO types with local evidence.
- Model topic name, cluster/environment context and key/value serialization; preserve dynamic topic expressions as partial.
- Create producer/consumer relations to local UCM symbols; use external topic resource selectors for other repositories.
- Expose topic/source/handler lookup keys for future discovery; never assume equal topic names mean same cluster.

## Non-goals
- No runtime execution of source, SQL, network calls or remote services.
- No global cross-repository linking during ingestion.
- Do not create a second storage graph or directly persist from adapters.

## Dependencies
Existing UCM Core, SourceAdapter registry, Evidence and incremental manifests. For resolver bindings, prerequisite schema/parsing capability.

## Priority
P1/P2. Build in parallel with discovery work after stable R1 core.
