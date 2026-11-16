# Design: Kafka topic declaration discovery

## Starting point
D07 now extracts typed Kafka topic resources and producers/consumers, but discovery._SUPPORTED still declares KAFKA_TOPIC UNSUPPORTED. Query-time Kafka ExternalReference cannot find declaration candidates even when D07 has a legitimate local definition.

## Decisions and integration
### D1
Inspect D07 UCM facts and define a strict predicate for a Kafka topic DECLARATION; exclude mere KafkaTemplate.send, listener subscriptions, dynamic expressions and client configurations from confirmed definitions.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D2
Extend repository-local discovery projection to project only supported typed declarations, with source UCM entity ID, snapshot/generation, exact topic key, optional cluster/namespace/environment and Evidence.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D3
Expose KAFKA_TOPIC exact lookup and selector normalization through existing C02/C04, with bounded fanout, authorization, explicit PARTIAL coverage and no confirmed runtime delivery edges.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D4
Version the discovery projector and support deterministic refresh, old-pinned generation reads and cache miss on updated generations without cross-repo ingest.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

### D5
Add synthetic multi-repository fixture and negative cases: same topic in two clusters, subscription without definition, dynamic topic, ambiguous names, missing generation.

Implementation details: reuse the existing typed UCM, SourceAnalysis, Evidence, Discovery and search generation contracts; fail closed where scope or provenance is unavailable. Use deterministic keys and bounded SQL operations rather than a new global graph.

## Data lifecycle
Treat UCM snapshots as immutable. Derived discovery/search generations may be rebuilt independently and must remain consistently pinned within one read-only REPEATABLE READ transaction. Selection of other repositories happens only in a trusted version context at query time, not ingestion.

## Security and failure modes
Untrusted source/configuration is never executed. Bounded budgets for memory, candidates and query time. Enforce repository grants before SQL; no source secrets in search projections, diagnostics or logs. On failures the current publication and previous derived generation remain readable.

## Compatibility
Do not break existing C01–C06 API signatures without an explicitly versioned migration and regression tests. Only introduce schema migration if strictly required. Existing migration files are immutable.

## Relevant code
src/code_crawler/discovery.py; src/code_crawler/external_candidates.py; src/code_crawler/kafka_adapter.py; src/code_crawler/kafka_java.py; tests/test_discovery_search.py; tests/integration/test_discovery_catalog_extended.py; docs/global-discovery-catalog.md; docs/external-reference-candidates.md
