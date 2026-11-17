# Kafka message intelligence (D07)

`KafkaSourceAdapter` augments the existing canonical Java SourceAdapter with
versioned Kafka facts. It uses the existing Java AST/symbols rather than a second
Java parser and preserves all selected Java/SQL profile output. Central ingestion
owns storage, publication and incremental reuse; the producer never connects to
Kafka or another repository.

Supported APIs, identity rules, uncertainty, evidence and limitations are
specified below. Dynamic topic/configuration
expressions never become concrete topic identities or definite runtime dependencies.

## Activation and compatibility

The CLI enables `KafkaSourceAdapter(java_adapter=JavaSourceAdapter(...))` for
canonical `index`/`index-sources`. The selected Java profile/dialect/schema inputs
remain unchanged. The wrapper owns `.java` and `.properties`; it must replace,
rather than accompany, a plain JavaSourceAdapter on the same suffix. Existing
standalone JavaSourceAdapter callers remain supported.

```python
registry = AdapterRegistry(
    (
        KafkaSourceAdapter(JavaSourceAdapter(profile="orm")),
        BpmnSourceAdapter(),
        OpenApiSourceAdapter(),
    )
)
```

Java parsing is shared through prepared `symbol_results()`: symbols profile caches
the original extractor result; higher profiles reuse their existing analyzer ASTs.
The wrapper forwards Java's immutable BPMN catalog exports and returns canonical
Java facts plus Kafka facts. It never writes to PostgreSQL. YAML remains owned by
OpenAPI; captured application YAML is read only through prepare_inventory.
Analyzer/capability version: `kafka/1`, `kafka.messages`, always PARTIAL.
The wrapper preserves the Java profile adapter key (for example java.orm); its
descriptor version combines Kafka/base versions and adds Kafka capabilities.
`adapters list` shows these active CLI Java profile variants.

## Supported syntax

Namespace/type checks use canonical Java symbols and explicit, unambiguous imports
or fully qualified known APIs. A same-named local type, unknown import, ambiguous
wildcard or shadowed receiver is not guessed to be Kafka. No classpath is loaded.

- Method-level `org.springframework.kafka.annotation.KafkaListener`: literal/final
  topics (including arrays), groupId, id, clientIdPrefix, containerFactory qualifier
  and literal properties overrides. One plain payload parameter or a single
  `ConsumerRecord<K,V>` parameter supplies declared DTO type candidates.
- `org.springframework.kafka.core.KafkaTemplate<K,V>.send(topic,...)` on a typed
  field/local/parameter receiver; direct literal topic or a supported final String
  constant supplies the resource name. Generic arguments supply declared key/value
  types; payload expressions are not executed or interpreted as runtime schemas.
- Apache `KafkaProducer<K,V>`/`Producer<K,V>.send(new ProducerRecord<>(topic,...))`.
  Passing a record variable, Message or dynamic expression leaves the topic partial.
- Apache `KafkaConsumer<K,V>`/`Consumer<K,V>.subscribe(List.of(...))`,
  `Arrays.asList(...)` or `Collections.singletonList(...)`; these are subscription
  sites, not inferred poll/record processing handlers.
- `new org.apache.kafka.clients.admin.NewTopic(topic,...)` records a declaration
  candidate, not deployment, actual broker existence or successful topic creation.
- Direct method-local `Properties` construction, literal `put` calls and recognized
  ProducerConfig/ConsumerConfig constants capture client bootstrap/group/client IDs
  and key/value serializer/deserializer classes. `.class` literals are retained.
  Configuration is snapshotted at client construction; later map changes do not
  rewrite a previous client's source candidate. Branch-dependent writes, assignment,
  aliases and method escapes invalidate the known map rather than guessing values.

Final String constants are resolved locally, including explicit static imports and
qualified local class fields. Cycles, ambiguous definitions, mutable fields,
placeholders `${...}`/`#{...}` and unsupported expressions yield unknown values.
String-only literal concatenation is supported within the budgets below.
Class-level KafkaListener/KafkaHandler dispatch, topicPattern/topicPartitions,
SpEL, classpath inheritance/proxies, TopicBuilder, sendDefault, record-variable
flow, custom factory wiring and actual broker operations are not resolved.
Class/pattern selectors have explicit diagnostics where recognized.

## Configuration candidates and resource identity

Captured application.properties/application.yml/application.yaml are explicit
source candidates. A single candidate in the source ancestors, repository root or
root `src/main/resources` layout supplies bootstrap servers, producer/consumer
serde, group/client IDs and literal `spring.profiles.active` as an environment
**hint**. Multiple candidates remain ambiguous. Profile-specific files are retained
as separate property source facts, never automatically activated by filename.
There is no inference of runtime property precedence, active deployment, custom
containerFactory or KafkaTemplate wiring. Listener literal properties override
source candidates; unknown override expressions clear the inferred candidate.

Properties support literal key=value lines, blank lines and #/! comments.
Continuation, duplicate keys and unsupported forms yield partial diagnostics and
no selected context. YAML uses the existing bounded safe syntax parser without
custom object construction/alias expansion; configuration lists/merge semantics,
Spring Config imports and profile activation logic are unsupported. Placeholder
values remain unknown. Only the configuration whitelist is projected: bootstrap,
key/value serializer/deserializer, group.id, client.id and environment. SASL,
passwords and unrelated properties are not copied into Kafka facts.

Each resource exposes exact topic, cluster/bootstrap and environment attributes.
Its qualified lookup key is `kafka.topic::` plus canonical JSON of these values.
If any dimension is unknown, the key also includes an opaque local endpoint/site
ID. Equal names alone never collapse unknown clusters/environments. Even a fully
specified key describes SOURCE_CANDIDATE configuration, not runtime identity;
resources from distinct syntax sites keep separate entity IDs and provenance.
No producer-to-consumer or cross-repository canonical edge is constructed.

Concrete topic names must match Kafka's ASCII `[A-Za-z0-9._-]`, length 1..249,
excluding `.` and `..`. Invalid literals are retained as source_literal with an
INVALID_TOPIC diagnostic; topic=null and no concrete external selector are emitted.

## UCM storage and uncertainty

Migration `0027_kafka_message_intelligence.sql` extends existing symbol and relation
registries. There are no parallel Kafka tables or arbitrary JSON fact payloads.
Canonical entity JSON Schema is updated; new symbols use stable repository/file/
owner/role/site-index logical keys. Repeating the same input gives the same facts.

| Symbol kind | Meaning |
| --- | --- |
| KAFKA_PRODUCER | Known producer API syntax site |
| KAFKA_CONSUMER | Listener declaration or explicit client subscription site |
| KAFKA_DECLARATION | NewTopic constructor declaration candidate |
| KAFKA_TOPIC | Concrete source resource or explicitly partial topic candidate |
| KAFKA_CONFIGURATION | Whitelisted literal property source |

KAFKA_HANDLER connects a site to its existing canonical METHOD/CONSTRUCTOR.
KAFKA_ATTRIBUTE connects typed scalar Values. Canonical validation checks Kafka
source/target symbol kinds, not just generic SYMBOL endpoint types.

KAFKA_PRODUCES_TO, KAFKA_CONSUMES_FROM and KAFKA_DECLARES_TOPIC resolve a concrete
source resource with **INFERRED** certainty. A dynamic/invalid name is PARTIAL,
UNKNOWN, has no target and retains a partial resource candidate. This is syntax
resolution, never proof of delivery, active subscription or deployed topic.

KAFKA_MESSAGE_TYPE points to a unique local declared CLASS with STATIC_PROVEN
certainty for the type syntax; missing/external/generic types are UNRESOLVED and
UNKNOWN. Explicitly ambiguous imports preserve candidates/AMBIGUOUS. A generic
type parameter cannot bind to a same-named repository class. KAFKA_SERDE uses
INFERRED even for a unique local serde class; external serde remains unresolved.
The raw key/value/serde type names are retained regardless of local availability.

Every Relation/ExternalReference includes Evidence and PARTIAL Coverage. Evidence
covers the Java syntax site, handler/receiver declaration and relevant captured
configuration or method-local Properties writes/constructor when available.
Canonical published_reader.get_evidence restores archived source bytes. Namespace
and import checks do not imply that a framework is installed or running.

Concrete topic references also produce deferred SymbolSelector external references
with the qualified resource key and UNKNOWN certainty. Another repository is never
consulted during indexing. These are future lookup keys; the global discovery
catalog/C04 supports explicit static NewTopic declaration candidates in discovery/3; runtime delivery remains unproven.
Local exact symbol lookup by qualified resource key is already supported.

## Incremental lifecycle, budgets and verification

Prepared identity includes the selected Java profile analysis identity, Kafka
version and sorted hashes of all captured Java/application config sources. Changes
conservatively invalidate the whole Kafka/Java wrapper scope; other adapter scopes
retain their existing rules. Explicit positive/negative config-path dependencies
are also recorded. Constant/DTO/factory availability changes and config addition,
removal or edits cannot silently reuse stale Kafka facts. Unchanged snapshots reuse
identical SourceAnalysis, diagnostics and graph facts. Producer failures preserve
the current canonical publication; storage failures follow central transaction rules.

The extra Kafka pass is bounded per file to 4 MiB, 100,000 AST nodes and depth 128.
It is suppressed with SOURCE_LIMIT diagnostics while preserving canonical Java
output. The underlying Java parser keeps its existing profile/failure contract.
Constant expansion is memoized, limited to 16 referenced declarations, expression
recursion depth 64 and 16 KiB UTF-8 per resulting literal. Application config is
limited to 1 MiB and the shared YAML parser budgets. Analysis and large result
combination run in worker threads; there is no network/filesystem/broker I/O in
Kafka analysis. No large-repository memory/performance claim is made.

Tests: tests/test_kafka_adapter.py and tests/integration/test_kafka_storage.py cover
Spring/Apache APIs, dynamic and invalid topics, cluster separation, local DTO/serde,
ambiguous/missing/generic types, constants, map construction/escape/assignment,
configuration candidates, malformed YAML/Java, budgets, AST sharing with BPMN,
PG15 migration/publication, archived Evidence, full/incremental equivalence, reuse,
version invalidation, config edits, consumer removal, independent repositories and
failed-producer preservation.

## Topic discovery (C10)

Discovery projector `discovery/3` публикует KAFKA_TOPIC definitions только для
static NewTopic declarations, не для producers/listeners/subscriptions. Exact
topic key и optional cluster/environment сохраняют D07 source identity; неизвестный
контекст не становится глобальным topic identity. C04 resolver/3 принимает
существующие JSON selectors и возвращает кандидатов из выбранных C03 snapshots.
Совпадение всегда PARTIAL/AMBIGUOUS: deployment и delivery не доказаны. Изменение
published snapshot/generation меняет cache identity; pinned old snapshots читают
свои старые declarations. Canonical Kafka facts не переписываются.
