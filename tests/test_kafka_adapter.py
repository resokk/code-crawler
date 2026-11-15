import asyncio
import json

import pytest
from test_source_adapters import REPO, source

from code_crawler.ingestion import UcmBatch
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.kafka_adapter import KafkaSourceAdapter
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.source_routing import source_language
from code_crawler.ucm import ExternalReference, Relation, RelationKind, Symbol

JAVA = """package app;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
class Order {}
class Handler {
 static final String TOPIC = "orders";
 KafkaTemplate<String, Order> kafka;
 @KafkaListener(topics=TOPIC, groupId="orders-group")
 void consume(Order order) {}
 void publish(Order order) { kafka.send(TOPIC, order); }
 void dynamic(String topic, Order order) { kafka.send(topic, order); }
}
"""
CONFIG = """spring.kafka.bootstrap-servers=broker-a:9092
spring.profiles.active=dev
spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=app.OrderSerializer
spring.kafka.consumer.value-deserializer=app.OrderDeserializer
spring.kafka.properties.sasl.password=must-not-be-exported
"""


def analyze(files, profile="symbols", other_adapters=()):
    async def run():
        adapter = KafkaSourceAdapter(JavaSourceAdapter(profile=profile))
        registry = AdapterRegistry((adapter, *other_adapters))
        sources = tuple(
            source(path, text, source_language(path, registry.languages) or "unknown")
            for path, text in files.items()
        )
        prepared = await registry.prepare(sources)
        output = await prepared(
            tuple(s for s in sources if registry.route(s.file.path))
        )
        facts = (
            *[s.file for s in sources],
            *[e for result in output for e in result.entities],
        )
        UcmBatch(repository_id=REPO, entities=facts)
        return output, facts, prepared

    return asyncio.run(run())


def symbols(facts, kind):
    return [e for e in facts if isinstance(e, Symbol) and e.symbol_kind == kind]


def attributes(facts, entity):
    by_id = {e.id: e for e in facts}
    return {
        by_id[r.resolution.target.id].name: by_id[r.resolution.target.id].literal
        for r in facts
        if isinstance(r, Relation)
        and r.relation_kind == RelationKind.KAFKA_ATTRIBUTE
        and r.source.id == entity.id
    }


def test_spring_listener_producer_dynamic_topic_and_dto():
    _output, facts, prepared = analyze(
        {"Handler.java": JAVA, "application.properties": CONFIG}
    )
    assert len(symbols(facts, "KAFKA_CONSUMER")) == 1
    assert len(symbols(facts, "KAFKA_PRODUCER")) == 2
    topics = symbols(facts, "KAFKA_TOPIC")
    assert len(topics) == 3
    known = [attributes(facts, s) for s in topics if s.name == "orders"]
    assert len(known) == 2
    assert all(
        a["topic"] == "orders"
        and a["cluster"] == "broker-a:9092"
        and a["environment"] == "dev"
        for a in known
    )
    dynamic = next(
        r
        for r in facts
        if isinstance(r, Relation)
        and r.relation_kind == RelationKind.KAFKA_PRODUCES_TO
        and r.resolution.status == "PARTIAL"
    )
    assert dynamic.resolution.target is None and dynamic.certainty == "UNKNOWN"
    assert (
        attributes(facts, next(s for s in topics if s.name == "dynamic topic"))["topic"]
        is None
    )
    types = [
        r
        for r in facts
        if isinstance(r, Relation)
        and r.relation_kind == RelationKind.KAFKA_MESSAGE_TYPE
        and r.resolution.status == "RESOLVED"
    ]
    assert types and all(
        next(s for s in facts if s.id == r.resolution.target.id).name == "Order"
        for r in types
    )
    assert all(
        r.evidence and r.coverage.status == "PARTIAL"
        for r in facts
        if isinstance(r, Relation) and r.relation_kind.value.startswith("KAFKA_")
    )
    assert any(
        isinstance(e, ExternalReference)
        and e.selector.qualified_name.startswith("kafka.topic::")
        for e in facts
    )
    assert "must-not-be-exported" not in json.dumps(
        [e.model_dump(mode="json") for e in facts]
    )
    assert analyze({"Handler.java": JAVA, "application.properties": CONFIG})[1] == facts
    assert prepared.analysis_version
    consumer = attributes(facts, symbols(facts, "KAFKA_CONSUMER")[0])
    assert (
        consumer["group.id"] == "orders-group"
        and consumer["value.deserializer"] == "app.OrderDeserializer"
    )
    producer = attributes(facts, symbols(facts, "KAFKA_PRODUCER")[0])
    assert producer["value.serializer"] == "app.OrderSerializer"


def test_same_topic_in_two_clusters_and_unknown_environments_are_distinct():
    text = """import org.springframework.kafka.annotation.KafkaListener;
class Handler {
 @KafkaListener(topics="same", properties={"bootstrap.servers=cluster-a"}) void a(String x) {}
 @KafkaListener(topics="same", properties={"bootstrap.servers=cluster-b"}) void b(String x) {}
}"""
    _, facts, _ = analyze({"Handler.java": text})
    topics = symbols(facts, "KAFKA_TOPIC")
    assert len(topics) == 2 and topics[0].qualified_name != topics[1].qualified_name
    assert {attributes(facts, s)["cluster"] for s in topics} == {
        "cluster-a",
        "cluster-b",
    }
    assert all(attributes(facts, s)["environment"] is None for s in topics)


def test_apache_producer_consumer_serde_and_topic_declaration():
    text = """import java.util.Properties;
import java.util.List;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.ProducerConfig;
import org.apache.kafka.clients.consumer.KafkaConsumer;
import org.apache.kafka.clients.admin.NewTopic;
import org.apache.kafka.common.serialization.StringSerializer;
class Order {}
class App { void run(Order payload) {
 Properties props = new Properties();
 props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,"broker-a");
 props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,StringSerializer.class);
 KafkaProducer<String,Order> producer = new KafkaProducer<>(props);
 props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,"broker-b");
 producer.send(new ProducerRecord<>("events", "key", payload));
 KafkaConsumer<String,Order> consumer = new KafkaConsumer<>(props);
 consumer.subscribe(List.of("events","audit"));
 NewTopic declared = new NewTopic("declared", 1, (short)1);
} }"""
    _, facts, _ = analyze({"App.java": text})
    assert len(symbols(facts, "KAFKA_PRODUCER")) == 1
    assert len(symbols(facts, "KAFKA_CONSUMER")) == 1
    assert len(symbols(facts, "KAFKA_DECLARATION")) == 1
    producer = attributes(facts, symbols(facts, "KAFKA_PRODUCER")[0])
    assert producer["bootstrap.servers"] == "broker-a"
    assert (
        producer["key.serializer"]
        == "org.apache.kafka.common.serialization.StringSerializer"
    )
    consumer = attributes(facts, symbols(facts, "KAFKA_CONSUMER")[0])
    assert consumer["bootstrap.servers"] == "broker-b"
    assert {s.name for s in symbols(facts, "KAFKA_TOPIC")} == {
        "events",
        "audit",
        "declared",
    }


@pytest.mark.parametrize(
    "imports",
    [
        "",
        "import other.KafkaListener; import other.KafkaTemplate;",
        "import org.springframework.kafka.annotation.*; import other.*;",
    ],
)
def test_names_without_unambiguous_framework_identity_are_not_kafka(imports):
    text = (
        imports
        + """class App { KafkaTemplate<String,String> sender;
 @KafkaListener(topics="x") void consume(String x) {}
 void publish() { sender.send("x","value"); }
}"""
    )
    _, facts, _ = analyze({"App.java": text})
    assert not symbols(facts, "KAFKA_CONSUMER") and not symbols(facts, "KAFKA_PRODUCER")


def test_shadowed_receiver_and_mutable_topic_are_not_guessed():
    text = """import org.springframework.kafka.core.KafkaTemplate;
class Custom { void send(String a,String b) {} }
class App { KafkaTemplate<String,String> sender;
 String topic="not-constant";
 void wrong(Custom sender) { sender.send("x","value"); }
 void actual() { this.sender.send(topic,"value"); }
}"""
    _, facts, _ = analyze({"App.java": text})
    assert len(symbols(facts, "KAFKA_PRODUCER")) == 1
    assert symbols(facts, "KAFKA_TOPIC")[0].name == "dynamic topic"


def test_static_cross_file_topic_constants_and_missing_external_type():
    text = """package app;
import static app.Topics.EVENTS;
import org.springframework.kafka.annotation.KafkaListener;
import missing.Dto;
class App { @KafkaListener(topics=EVENTS) void accept(Dto payload) {} }"""
    _, facts, _ = analyze(
        {
            "App.java": text,
            "Topics.java": 'package app; class Topics { static final String EVENTS="events"; }',
        }
    )
    assert symbols(facts, "KAFKA_TOPIC")[0].name == "events"
    assert any(
        isinstance(r, Relation)
        and r.relation_kind == RelationKind.KAFKA_MESSAGE_TYPE
        and r.resolution.status == "UNRESOLVED"
        for r in facts
    )


def test_bad_config_and_syntax_are_partial():
    _, facts, _ = analyze(
        {
            "App.java": JAVA,
            "application.properties": "spring.kafka.bootstrap-servers=a\nspring.kafka.bootstrap-servers=b",
        }
    )
    assert all(
        attributes(facts, s)["cluster"] is None for s in symbols(facts, "KAFKA_TOPIC")
    )
    assert any(
        d.code == "kafka.CONFIG_PARTIAL"
        for e in facts
        if e.entity_type == "SOURCE_ANALYSIS"
        for d in e.diagnostics
    )
    _, facts, _ = analyze({"Bad.java": "class {"})
    assert not symbols(facts, "KAFKA_TOPIC")
    assert any(
        d.code == "kafka.JAVA_PARSE_ERROR"
        for e in facts
        if e.entity_type == "SOURCE_ANALYSIS"
        for d in e.diagnostics
    )


def test_generic_type_parameter_does_not_bind_to_same_named_class():
    text = """import org.springframework.kafka.annotation.KafkaListener;
class Order {}
class App { @KafkaListener(topics="x") <Order> void accept(Order value) {} }"""
    _, facts, _ = analyze({"App.java": text})
    links = [
        r
        for r in facts
        if isinstance(r, Relation)
        and r.relation_kind == RelationKind.KAFKA_MESSAGE_TYPE
    ]
    assert links and all(r.resolution.status == "UNRESOLVED" for r in links)


def test_nested_class_or_lambda_calls_do_not_belong_to_outer_method():
    text = """import org.springframework.kafka.core.KafkaTemplate;
class App { KafkaTemplate<String,String> sender;
 void outer() {
  Runnable task = () -> sender.send("lambda","x");
  class Inner { void run() { sender.send("nested","x"); } }
  sender.send("outer","x");
 }
}"""
    _, facts, _ = analyze({"App.java": text})
    assert "lambda" not in {s.name for s in symbols(facts, "KAFKA_TOPIC")}
    outer = [
        s
        for s in symbols(facts, "KAFKA_PRODUCER")
        if s.qualified_name.startswith("App.outer:")
    ]
    assert len(outer) == 1


def test_property_map_escape_branch_and_reassignment_do_not_guess_cluster():
    template = """import java.util.Properties;
import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
class App { void configure(Properties p) {} void run(boolean flag) {
 Properties p = new Properties(); p.put("bootstrap.servers","a");
 CHANGE
 KafkaProducer<String,String> producer = new KafkaProducer<>(p);
 producer.send(new ProducerRecord<>("x","value"));
} }"""
    for change in (
        "configure(p);",
        'if(flag) p.put("bootstrap.servers","b");',
        "p = other();",
        'Properties alias = p; alias.put("bootstrap.servers","b");',
    ):
        _, facts, _ = analyze({"App.java": template.replace("CHANGE", change)})
        assert all(
            attributes(facts, s)["cluster"] is None
            for s in symbols(facts, "KAFKA_TOPIC")
        )


def test_ambiguous_dto_and_placeholder_topic_stay_explicit():
    text = """package app;
import org.springframework.kafka.annotation.KafkaListener;
import one.Dto; import two.Dto;
class App { @KafkaListener(topics="${topic}") void accept(Dto payload) {} }"""
    _, facts, _ = analyze(
        {
            "App.java": text,
            "One.java": "package one; class Dto {}",
            "Two.java": "package two; class Dto {}",
        }
    )
    assert symbols(facts, "KAFKA_TOPIC")[0].name == "dynamic topic"
    assert any(
        isinstance(r, Relation)
        and r.relation_kind == RelationKind.KAFKA_MESSAGE_TYPE
        and r.resolution.status == "AMBIGUOUS"
        and len(r.resolution.candidates) == 2
        for r in facts
    )


def test_ast_is_reused_for_kafka_java_and_bpmn_catalog(monkeypatch):
    from code_crawler import java_adapter
    from code_crawler.bpmn_adapter import BpmnSourceAdapter

    original = java_adapter.extract
    calls = []

    def counting(source):
        calls.append(source.file.path)
        return original(source)

    monkeypatch.setattr(java_adapter, "extract", counting)
    analyze({"Handler.java": JAVA}, other_adapters=(BpmnSourceAdapter(),))
    assert calls == ["Handler.java"]


def test_yaml_configuration_and_ambiguous_config_sources():
    from code_crawler.openapi_adapter import OpenApiSourceAdapter

    config = """spring:
  profiles:
    active: stage
  kafka:
    bootstrap-servers: cluster-yaml
    consumer:
      value-deserializer: app.OrderDeserializer
"""
    _, facts, _ = analyze(
        {"Handler.java": JAVA, "application.yaml": config},
        other_adapters=(OpenApiSourceAdapter(),),
    )
    assert all(
        attributes(facts, s)["cluster"] == "cluster-yaml"
        for s in symbols(facts, "KAFKA_TOPIC")
    )
    assert all(
        attributes(facts, s)["environment"] == "stage"
        for s in symbols(facts, "KAFKA_TOPIC")
    )
    _, facts, _ = analyze(
        {
            "Handler.java": JAVA,
            "application.yaml": config,
            "application.properties": CONFIG,
        },
        other_adapters=(OpenApiSourceAdapter(),),
    )
    assert all(
        attributes(facts, s)["cluster"] is None for s in symbols(facts, "KAFKA_TOPIC")
    )
    assert any(
        d.code == "kafka.AMBIGUOUS_CONFIGURATION"
        for e in facts
        if e.entity_type == "SOURCE_ANALYSIS"
        for d in e.diagnostics
    )


def test_unsafe_yaml_and_dynamic_config_never_select_effective_context():
    from code_crawler.openapi_adapter import OpenApiSourceAdapter

    for config in (
        "spring: [",
        'spring: !!python/object/apply:os.system ["ignored"]',
        "spring: &a {kafka: x}\nmore: *a",
    ):
        _, facts, _ = analyze(
            {"Handler.java": JAVA, "application.yaml": config},
            other_adapters=(OpenApiSourceAdapter(),),
        )
        assert all(
            attributes(facts, s)["cluster"] is None
            for s in symbols(facts, "KAFKA_TOPIC")
        )
        assert any(
            d.code == "kafka.CONFIG_PARTIAL"
            for e in facts
            if e.entity_type == "SOURCE_ANALYSIS"
            for d in e.diagnostics
        )
    _, facts, _ = analyze(
        {
            "Handler.java": JAVA,
            "application.properties": "spring.kafka.bootstrap-servers=${BROKER}",
        }
    )
    assert all(
        attributes(facts, s)["cluster"] is None for s in symbols(facts, "KAFKA_TOPIC")
    )


def test_kafka_pass_budget_does_not_remove_canonical_java_facts(monkeypatch):
    from code_crawler import kafka_java

    monkeypatch.setattr(kafka_java, "MAX_BYTES", 20)
    _, facts, _ = analyze({"Handler.java": JAVA})
    assert not symbols(facts, "KAFKA_PRODUCER")
    assert symbols(facts, "METHOD")
    assert any(
        d.code == "kafka.SOURCE_LIMIT"
        for e in facts
        if e.entity_type == "SOURCE_ANALYSIS"
        for d in e.diagnostics
    )


def test_listener_unknown_pattern_and_dynamic_override_are_partial():
    text = """import org.springframework.kafka.annotation.KafkaListener;
class App { @KafkaListener(topicPattern="orders.*",properties={"bootstrap.servers="+unknown()}) void accept(String value) {} }"""
    _, facts, _ = analyze({"App.java": text, "application.properties": CONFIG})
    assert all(
        attributes(facts, s)["cluster"] is None
        and attributes(facts, s)["topic"] is None
        for s in symbols(facts, "KAFKA_TOPIC")
    )


def test_serde_reference_is_local_candidate_not_runtime_proof():
    _, facts, _ = analyze(
        {
            "Handler.java": JAVA + "\nclass OrderSerializer {}",
            "application.properties": CONFIG,
        }
    )
    serde = [
        r
        for r in facts
        if isinstance(r, Relation) and r.relation_kind == RelationKind.KAFKA_SERDE
    ]
    assert serde and any(
        r.resolution.status == "RESOLVED" and r.certainty == "INFERRED" for r in serde
    )
    assert any(
        r.resolution.status == "UNRESOLVED" and r.certainty == "UNKNOWN" for r in serde
    )


def test_invalid_handler_target_is_rejected_by_canonical_contract():
    from code_crawler.ucm import EntityRef, Resolution, validate_relation_endpoints

    _, facts, _ = analyze({"Handler.java": JAVA})
    handler = next(
        r
        for r in facts
        if isinstance(r, Relation) and r.relation_kind == RelationKind.KAFKA_HANDLER
    )
    topic = symbols(facts, "KAFKA_TOPIC")[0]
    invalid = handler.model_copy(
        update={
            "resolution": Resolution(
                status="RESOLVED",
                target=EntityRef(id=topic.id, entity_type=topic.entity_type),
            )
        }
    )
    with pytest.raises(ValueError, match="Kafka relation symbol kinds"):
        validate_relation_endpoints(invalid, {e.id: e for e in facts})


@pytest.mark.parametrize("topic", [".", "..", "contains space", "юникод", "x" * 250])
def test_invalid_topic_literal_is_source_data_not_resource_identity(topic):
    text = (
        "import org.springframework.kafka.annotation.KafkaListener; class App { @KafkaListener(topics="
        + json.dumps(topic, ensure_ascii=False)
        + ") void accept(String x) {} }"
    )
    _, facts, _ = analyze({"App.java": text})
    resource = symbols(facts, "KAFKA_TOPIC")[0]
    assert attributes(facts, resource)["topic"] is None
    assert attributes(facts, resource)["source_literal"] == topic
    assert not any(
        isinstance(e, ExternalReference)
        and e.selector.qualified_name.startswith("kafka.topic::")
        for e in facts
    )


def test_constant_expansion_is_bounded_and_cyclic_constants_stay_unknown(monkeypatch):
    from code_crawler import kafka_java

    monkeypatch.setattr(kafka_java, "MAX_LITERAL_BYTES", 8)
    text = """import org.springframework.kafka.annotation.KafkaListener;
class App { static final String A="abcd"; static final String B=A+A; static final String C=B+B;
 static final String X=Y; static final String Y=X;
 @KafkaListener(topics={C,X}) void accept(String x) {} }"""
    _, facts, _ = analyze({"App.java": text})
    assert all(
        attributes(facts, s)["topic"] is None for s in symbols(facts, "KAFKA_TOPIC")
    )


def test_ast_depth_budget_and_class_listener_are_explicit(monkeypatch):
    from code_crawler import kafka_java

    monkeypatch.setattr(kafka_java, "MAX_DEPTH", 4)
    _, facts, _ = analyze({"Handler.java": JAVA})
    assert not symbols(facts, "KAFKA_PRODUCER")
    assert any(
        d.code == "kafka.SOURCE_LIMIT"
        for e in facts
        if e.entity_type == "SOURCE_ANALYSIS"
        for d in e.diagnostics
    )
