# Design: Kafka producers, consumers, topics and schema lineage

## Baseline
Kafka dependencies are not represented as local UCM graph or discovery entries.

## Architecture
### Decision 1
Extract topic declarations and configuration identities from supported Java Spring Kafka and Kafka client APIs.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 2
Detect producer sends, listener/consumer handlers, serde and message DTO types with local evidence.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 3
Model topic name, cluster/environment context and key/value serialization; preserve dynamic topic expressions as partial.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 4
Create producer/consumer relations to local UCM symbols; use external topic resource selectors for other repositories.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 5
Expose topic/source/handler lookup keys for future discovery; never assume equal topic names mean same cluster.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

## SourceAdapter lifecycle
Detect file → safe parse → AST/language-specific facts → local reference resolution → UCM Batch → centralized PostgreSQL staging/validation/publication. Record file ownership and negative/positive dependencies for incremental reanalysis.

## Security and failure policy
No network lookups by default, no execution, no trust in input code or metadata. Constrain parser complexity and return diagnostics on malformed input. Failed analysis must not replace a currently published snapshot.

## Compatibility and tests
Add new UCM EntityType/RelationKind only if necessary, using forward migrations. Preserve existing Java/SQL/BPMN facts and compare full vs incremental output on same fixture.

## Resolved implementation contract

A dedicated KafkaSourceAdapter wraps the selected JavaSourceAdapter, sharing its
canonical JavaSymbolsResult ASTs via symbol_results(). It owns the same `.java`
route plus `.properties`, preserves Java profile adapter keys, adds versioned
Kafka capabilities, forwards BPMN catalog exports and combines facts in worker
threads. The standalone Java adapter remains available. YAML/other sources are
captured inventory inputs, not competing suffix registrations.

Migration 0027 extends existing Symbol kinds and Relation endpoints; storage stays
in normalized UCM tables. Source site, configuration and topic Symbols carry typed
scalar Values and exact captured SourceRange/Evidence. KAFKA_HANDLER connects sites
to existing canonical methods/constructors; canonical validation enforces source
and target Symbol subtypes. DTO type relations resolve only unambiguous local
classes; serde classes remain inferred even if local. Generic/missing/ambiguous
cases retain explicit Resolution and candidates.

Topic relations are source candidates with INFERRED certainty. Dynamic, invalid
or unsupported selectors are PARTIAL/UNKNOWN with no concrete target. Cluster,
environment and topic form qualified resource lookup keys; missing dimensions add
an opaque local site ID. External topic SymbolSelectors are always deferred,
UNKNOWN, and never consult another repository. Equal topic names cannot prove a
shared cluster or producer-consumer relationship. Global discovery/C04 Kafka
resolution remains a separate extension; exact local symbol lookup is tested.

Supported Spring method-level KafkaListener/KafkaTemplate and Apache
ProducerRecord/KafkaProducer/KafkaConsumer.subscribe/NewTopic syntax is documented
in docs/kafka-message-intelligence.md. Source configuration candidates come from
literal application properties/YAML and direct method-local Properties puts,
with construction-time snapshots. Placeholder, branch, alias, escape, reassignment,
custom factory and runtime behavior are never treated as effective wiring.

Prepared identity includes sorted Java/config hashes and analyzer versions, so
local constants, types and configuration changes conservatively invalidate the
whole wrapper scope. Positive/negative config dependencies are also retained.
Other producers keep their own invalidation rules. The integration fixture checks
unchanged reuse, config edits, full vs incremental fact equality, analyzer upgrade,
consumer removal, independent publications and preservation on detector failure.

Kafka analysis is limited to 4 MiB/100000 AST nodes/depth 128 per file; oversized
Kafka passes yield diagnostics without removing Java facts. Memoized string
constants have 16-reference, 64-expression-depth and 16 KiB literal budgets.
Configuration is limited to 1 MiB and shared safe YAML parser budgets. No broker,
network, ambient filesystem, source execution or direct adapter SQL is used.
