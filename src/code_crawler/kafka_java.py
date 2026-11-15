"""Conservative Kafka syntax facts over already extracted canonical Java ASTs."""

import json
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass

from tree_sitter import Node

from code_crawler import java
from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.java_calls import _erase, _modifiers
from code_crawler.java_symbols import JavaSymbolsResult
from code_crawler.jpa_catalog import arguments
from code_crawler.source_adapters import AdapterFileResult
from code_crawler.ucm import (
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    Relation,
    RelationKind,
    Resolution,
    SourceDiagnostic,
    Symbol,
    SymbolSelector,
    Value,
    logical_id,
)

VERSION = "kafka/1"
MAX_BYTES = 4 * 1024 * 1024
MAX_NODES = 100000
MAX_DEPTH = 128
MAX_LITERAL_BYTES = 16384
CAPABILITY = Coverage(
    capability="kafka.messages",
    analyzer_version=VERSION,
    status="PARTIAL",
    reasons=(
        "Bounded Java Kafka declarations and API syntax; runtime delivery, Spring wiring and deployment are not proved.",
    ),
)
LISTENER = "org.springframework.kafka.annotation.KafkaListener"
TEMPLATE = "org.springframework.kafka.core.KafkaTemplate"
PRODUCERS = {
    "org.apache.kafka.clients.producer.KafkaProducer",
    "org.apache.kafka.clients.producer.Producer",
    TEMPLATE,
}
CONSUMERS = {
    "org.apache.kafka.clients.consumer.KafkaConsumer",
    "org.apache.kafka.clients.consumer.Consumer",
}
RECORD = "org.apache.kafka.clients.producer.ProducerRecord"
CONSUMER_RECORD = "org.apache.kafka.clients.consumer.ConsumerRecord"
NEW_TOPIC = "org.apache.kafka.clients.admin.NewTopic"
KNOWN = {
    LISTENER,
    TEMPLATE,
    *PRODUCERS,
    *CONSUMERS,
    RECORD,
    CONSUMER_RECORD,
    NEW_TOPIC,
    "java.util.Properties",
    "java.util.Map",
    "java.util.List",
    "java.util.Arrays",
    "java.util.Collections",
    "org.springframework.messaging.Message",
    "org.springframework.kafka.support.Acknowledgment",
    "org.apache.kafka.clients.producer.ProducerConfig",
    "org.apache.kafka.clients.consumer.ConsumerConfig",
    "org.springframework.kafka.annotation.TopicPartition",
}
KNOWN |= {
    "org.apache.kafka.common.serialization." + name
    for name in (
        "StringSerializer",
        "StringDeserializer",
        "ByteArraySerializer",
        "ByteArrayDeserializer",
        "LongSerializer",
        "LongDeserializer",
        "IntegerSerializer",
        "IntegerDeserializer",
    )
}
CONFIG_KEYS = {
    "bootstrap.servers",
    "key.serializer",
    "value.serializer",
    "key.deserializer",
    "value.deserializer",
    "group.id",
    "client.id",
}
CONFIG_CONSTANTS = {
    "BOOTSTRAP_SERVERS_CONFIG": "bootstrap.servers",
    "KEY_SERIALIZER_CLASS_CONFIG": "key.serializer",
    "VALUE_SERIALIZER_CLASS_CONFIG": "value.serializer",
    "KEY_DESERIALIZER_CLASS_CONFIG": "key.deserializer",
    "VALUE_DESERIALIZER_CLASS_CONFIG": "value.deserializer",
    "GROUP_ID_CONFIG": "group.id",
    "CLIENT_ID_CONFIG": "client.id",
}


def walk(node: Node) -> Iterator[Node]:
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        if current != node and current.type in (
            "class_declaration",
            "interface_declaration",
            "record_declaration",
            "class_body",
            "method_declaration",
            "constructor_declaration",
            "lambda_expression",
        ):
            continue
        pending.extend(reversed(current.named_children))


@dataclass
class Unit:
    source: SourceInput
    result: JavaSymbolsResult
    types: dict[str, list[Symbol]]
    symbols: dict[str, Symbol]

    def __post_init__(self) -> None:
        self.extractor = self.result._extractor
        self.root = self.extractor.parsed._tree.root_node
        self.scopes = {node.id: scope for node, scope in self.extractor.nodes}
        self.package = ""
        self.imports = defaultdict(list)
        self.wildcards = []
        self.static_imports = defaultdict(list)
        for node in self.root.named_children:
            text = java._text(node)
            if node.type == "package_declaration":
                self.package = text.removeprefix("package").strip().rstrip(";").strip()
            if node.type == "import_declaration":
                if match := re.fullmatch(r"import\s+static\s+([\w.$]+)\s*;", text):
                    self.static_imports[match[1].rsplit(".", 1)[-1]].append(match[1])
                elif match := re.fullmatch(r"import\s+([\w.$]+)\s*;", text):
                    self.imports[match[1].rsplit(".", 1)[-1]].append(match[1])
                elif match := re.fullmatch(r"import\s+([\w.$]+)\.\*\s*;", text):
                    self.wildcards.append(match[1])

    def qualify(self, name: str) -> str | None:
        name = _erase(name)
        if name in self.types or name in KNOWN:
            return name
        local = f"{self.package}.{name}".lstrip(".")
        if local in self.types:
            return local
        head, _, tail = name.partition(".")
        if imported := self.imports.get(head):
            options = {item + ("." + tail if tail else "") for item in imported}
            return next(iter(options)) if len(options) == 1 else None
        options = {f"{package}.{name}" for package in self.wildcards} & (
            self.types.keys() | KNOWN
        )
        return (
            next(iter(options))
            if len(options) == 1 and len(self.wildcards) == 1
            else None
        )

    def resolve(
        self, node: Node | None, fallback_scope: str | None = None
    ) -> Symbol | None:
        if node is None:
            return None
        this_field = False
        if node.type == "field_access":
            obj = node.child_by_field_name("object")
            if obj is None or obj.type != "this":
                return None
            node = node.child_by_field_name("field")
            this_field = True
        if node.type != "identifier":
            return None
        if declaration := self.extractor.declarations.get(node.id):
            return declaration[0]
        scope = self.scopes.get(node.id, fallback_scope)
        if scope is None:
            return None
        matches = self.extractor.lookup(
            java._text(node),
            scope,
            node.start_byte,
            {"FIELD", "LOCAL_VARIABLE", "PARAMETER"},
            this_field=this_field,
        )
        return matches[0] if len(matches) == 1 else None

    def annotation(self, node: Node, name: str) -> Iterator[Node]:
        modifiers = next(
            (n for n in node.named_children if n.type == "modifiers"), None
        )
        for child in modifiers.named_children if modifiers else ():
            if child.type in ("annotation", "marker_annotation"):
                qualified = self.qualify(java._text(child.child_by_field_name("name")))
                if qualified == name and qualified not in self.types:
                    yield child


class Collector:
    def __init__(
        self, pairs: tuple[tuple[SourceInput, JavaSymbolsResult], ...]
    ) -> None:
        self.types = defaultdict(list)
        self.symbols = {}
        for _, result in pairs:
            if result.diagnostics:
                continue
            for symbol in result.declared:
                if isinstance(symbol, Symbol):
                    self.symbols[symbol.id] = symbol
                    if symbol.symbol_kind == "CLASS":
                        self.types[symbol.qualified_name].append(symbol)
        self.units = {
            source.file.path: Unit(source, result, self.types, self.symbols)
            for source, result in pairs
        }
        self.limited = set()
        for path, unit in self.units.items():
            pending = [(unit.root, 0)]
            count = 0
            if len(unit.source.content) > MAX_BYTES:
                self.limited.add(path)
                continue
            while pending:
                node, depth = pending.pop()
                count += 1
                if count > MAX_NODES or depth > MAX_DEPTH:
                    self.limited.add(path)
                    break
                pending.extend((child, depth + 1) for child in node.named_children)
        self.constants = defaultdict(list)
        self.constant_values = {}
        for unit in self.units.values():
            if unit.result.diagnostics or unit.source.file.path in self.limited:
                continue
            for symbol in unit.result.declared:
                if not isinstance(symbol, Symbol) or symbol.symbol_kind != "FIELD":
                    continue
                node = unit.extractor.symbol_nodes[symbol.id]
                declaration = node if node.type == "field_declaration" else node.parent
                if declaration and "final" in _modifiers(declaration):
                    value = node.child_by_field_name("value")
                    if value:
                        self.constants[symbol.qualified_name].append(
                            (unit, value, symbol)
                        )

    def string(
        self,
        unit: Unit,
        node: Node | None,
        scope: str | None,
        seen: frozenset[str] = frozenset(),
        depth: int = 0,
    ) -> str | None:
        if node is None or len(seen) > 16 or depth > 64:
            return None
        if node.type == "string_literal":
            try:
                value = java._literal(node)
                if len(value.encode("utf-8")) > MAX_LITERAL_BYTES:
                    return None
                return (
                    value
                    if value.strip() and not any(c in value for c in ("${", "#{", "\0"))
                    else None
                )
            except ValueError:
                return None
        if node.type == "parenthesized_expression" and len(node.named_children) == 1:
            return self.string(unit, node.named_children[0], scope, seen, depth + 1)
        if (
            node.type == "binary_expression"
            and java._text(node.child_by_field_name("operator")) == "+"
        ):
            left = self.string(
                unit, node.child_by_field_name("left"), scope, seen, depth + 1
            )
            right = self.string(
                unit, node.child_by_field_name("right"), scope, seen, depth + 1
            )
            if (
                left is not None
                and right is not None
                and len(left.encode("utf-8")) + len(right.encode("utf-8"))
                <= MAX_LITERAL_BYTES
            ):
                return left + right
            return None
        symbol = unit.resolve(node, scope)
        names = [symbol.qualified_name] if symbol else []
        text = java._text(node)
        if not names and node.type == "identifier":
            names = unit.static_imports.get(text, [])
        if not names and node.type == "field_access":
            owner, _, field = text.rpartition(".")
            if qualified := unit.qualify(owner):
                names = [qualified + "." + field]
        candidates = [entry for name in names for entry in self.constants.get(name, ())]
        if len(candidates) != 1:
            return None
        other, value, declaration = candidates[0]
        if declaration.id in seen:
            return None
        if declaration.id not in self.constant_values:
            self.constant_values[declaration.id] = self.string(
                other, value, declaration.scope_id, seen | {declaration.id}, depth + 1
            )
        return self.constant_values[declaration.id]

    def strings(
        self, unit: Unit, node: Node | None, scope: str | None
    ) -> tuple[str | None, ...]:
        if node is None:
            return (None,)
        items = (
            node.named_children
            if node.type in ("element_value_array_initializer", "array_initializer")
            else (node,)
        )
        return tuple(
            dict.fromkeys(self.string(unit, item, scope) for item in items)
        ) or (None,)

    def analyze(
        self,
        path: str,
        config: dict[str, str],
        config_evidence: tuple[Evidence, ...],
        dependencies: tuple[str, ...],
    ) -> AdapterFileResult:
        return _FileCollector(
            self, self.units[path], config, config_evidence, dependencies
        ).collect()


class _FileCollector:
    def __init__(
        self,
        collector: Collector,
        unit: Unit,
        config: dict[str, str],
        evidence: tuple[Evidence, ...],
        dependencies: tuple[str, ...],
    ) -> None:
        self.collector, self.unit, self.config, self.config_evidence = (
            collector,
            unit,
            config,
            evidence,
        )
        self.dependencies = dependencies
        self.entities = []
        self.diagnostics = []
        self.counts = defaultdict(int)
        self.active_proof = ()

    def base(self, kind: EntityType, key: object, name: str, node: Node) -> dict:
        key = json.dumps(
            ["kafka", self.unit.source.file.path, key],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return {
            "repository_id": self.unit.source.file.repository_id,
            "id": logical_id(self.unit.source.file.repository_id, kind, key),
            "logical_key": key,
            "name": name,
            "source_range": self.unit.extractor.range(node),
        }

    def proof(self, node: Node, rule: str) -> Evidence:
        return Evidence(
            source_range=self.unit.extractor.range(node),
            analyzer="kafka",
            analyzer_version=VERSION,
            rule=rule,
            description="Explicit Java Kafka syntax; runtime wiring, delivery and deployment are not asserted.",
        )

    def evidence(self, node: Node, rule: str) -> tuple[Evidence, ...]:
        return (self.proof(node, rule), *self.active_proof)

    def diagnostic(self, node: Node, code: str, message: str) -> None:
        self.diagnostics.append(
            SourceDiagnostic(
                severity="WARNING",
                code="kafka." + code,
                message=message,
                source_range=self.unit.extractor.range(node),
            )
        )

    def link(
        self,
        kind: RelationKind,
        origin,
        target,
        node: Node,
        key: object,
        certainty=Certainty.STATIC_PROVEN,
        status="RESOLVED",
        reason=None,
        candidates=(),
    ) -> None:
        def ref(entity):
            return EntityRef(id=entity.id, entity_type=entity.entity_type)

        self.entities.append(
            Relation(
                **self.base(EntityType.RELATION, [kind.value, key], kind.value, node),
                relation_kind=kind,
                source=ref(origin),
                resolution=Resolution(
                    status=status,
                    target=ref(target) if target else None,
                    reason=reason,
                    candidates=tuple(ref(c) for c in candidates),
                ),
                certainty=certainty,
                evidence=self.evidence(node, kind.value),
                coverage=CAPABILITY,
            )
        )

    def attr(self, symbol: Symbol, name: str, value, node: Node) -> None:
        item = Value(
            **self.base(EntityType.VALUE, [symbol.id, name], name, node),
            value_kind="LITERAL",
            literal=value,
        )
        self.entities.append(item)
        self.link(RelationKind.KAFKA_ATTRIBUTE, symbol, item, node, [symbol.id, name])

    def message_type(
        self,
        endpoint: Symbol,
        name: str | None,
        role: str,
        node: Node,
        kind: RelationKind = RelationKind.KAFKA_MESSAGE_TYPE,
    ) -> None:
        if not name:
            return
        self.attr(endpoint, role, name, node)
        qualified = self.unit.qualify(name)
        masked = False
        parent = node
        while parent:
            parameters = next(
                (c for c in parent.named_children if c.type == "type_parameters"), None
            )
            if parameters and any(
                java._text(n.named_children[0]) == _erase(name)
                for n in parameters.named_children
                if n.named_children
            ):
                qualified = None
                masked = True
            parent = parent.parent
        names = (
            (qualified,)
            if qualified
            else tuple(self.unit.imports.get(_erase(name), ()))
        )
        candidates = sorted(
            (
                symbol
                for candidate in names
                for symbol in self.collector.types.get(candidate, ())
            )
            if not masked
            else (),
            key=lambda e: e.id,
        )
        self.link(
            kind,
            endpoint,
            candidates[0] if len(candidates) == 1 else None,
            node,
            [endpoint.id, role],
            certainty=(
                Certainty.INFERRED
                if kind == RelationKind.KAFKA_SERDE
                else Certainty.STATIC_PROVEN
            )
            if len(candidates) == 1
            else Certainty.UNKNOWN,
            status="RESOLVED"
            if len(candidates) == 1
            else "AMBIGUOUS"
            if candidates
            else "UNRESOLVED",
            reason=None
            if len(candidates) == 1
            else "Type is external, generic, missing or ambiguous",
            candidates=candidates if len(candidates) > 1 else (),
        )

    def endpoint(
        self,
        owner: Symbol,
        node: Node,
        direction: str,
        topics: tuple[str | None, ...],
        api: str,
        config: dict[str, str],
        key_type: str | None = None,
        value_type: str | None = None,
        qualifier: str | None = None,
        proofs: tuple[Evidence, ...] | None = None,
    ) -> None:
        self.active_proof = self.config_evidence if proofs is None else proofs
        index = self.counts[owner.id, direction]
        self.counts[owner.id, direction] += 1
        key = [owner.id, direction, index]
        endpoint = Symbol(
            **self.base(EntityType.SYMBOL, ["endpoint", key], api, node),
            symbol_kind="KAFKA_" + direction,
            qualified_name=owner.qualified_name
            + ":kafka:"
            + direction.lower()
            + ":"
            + str(index),
        )
        self.entities.append(endpoint)
        self.link(RelationKind.KAFKA_HANDLER, endpoint, owner, node, endpoint.id)
        self.attr(endpoint, "api", api, node)
        self.attr(endpoint, "configuration_status", "SOURCE_CANDIDATE", node)
        if qualifier:
            self.attr(endpoint, "factory", qualifier, node)
        self.message_type(endpoint, key_type, "key_type", node)
        self.message_type(endpoint, value_type, "value_type", node)
        for name in sorted(
            (CONFIG_KEYS | {"listener.id", "client.id"}) & config.keys()
        ):
            if name.endswith(("serializer", "deserializer")):
                self.message_type(
                    endpoint, config[name], name, node, RelationKind.KAFKA_SERDE
                )
            else:
                self.attr(endpoint, name, config[name], node)
        environment = config.get("environment")
        cluster = config.get("bootstrap.servers")
        self.attr(endpoint, "environment", environment, node)
        for topic_index, topic in enumerate(topics):
            literal_topic = topic
            if topic is not None and (
                not re.fullmatch(r"[A-Za-z0-9._-]{1,249}", topic)
                or topic in (".", "..")
            ):
                self.diagnostic(
                    node,
                    "INVALID_TOPIC",
                    "Literal topic is not a valid Kafka topic name; no concrete identity is asserted.",
                )
                topic = None
            identity = [cluster, environment, topic]
            # Unknown context/site never collapses into an identity shared by name.
            context = (
                identity
                if cluster and environment and topic
                else [*identity, "site", endpoint.id, topic_index]
            )
            resource = Symbol(
                **self.base(
                    EntityType.SYMBOL,
                    ["topic", endpoint.id, topic_index],
                    topic or "dynamic topic",
                    node,
                ),
                symbol_kind="KAFKA_TOPIC",
                qualified_name="kafka.topic::"
                + json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            )
            self.entities.append(resource)
            self.attr(resource, "topic", topic, node)
            if literal_topic is not None and topic is None:
                self.attr(resource, "source_literal", literal_topic, node)
            self.attr(resource, "cluster", cluster, node)
            self.attr(resource, "environment", environment, node)
            self.attr(
                resource,
                "status",
                "PARTIAL"
                if topic is None or not cluster or not environment
                else "SOURCE_CANDIDATE",
                node,
            )
            kind = (
                RelationKind.KAFKA_PRODUCES_TO
                if direction == "PRODUCER"
                else RelationKind.KAFKA_CONSUMES_FROM
                if direction == "CONSUMER"
                else RelationKind.KAFKA_DECLARES_TOPIC
            )
            self.link(
                kind,
                endpoint,
                resource if topic else None,
                node,
                [endpoint.id, topic_index],
                certainty=Certainty.INFERRED if topic else Certainty.UNKNOWN,
                status="RESOLVED" if topic else "PARTIAL",
                reason=None
                if topic
                else "Topic expression is dynamic; no concrete topic identity",
                candidates=(resource,) if topic is None else (),
            )
            if topic:
                self.entities.append(
                    ExternalReference(
                        **self.base(
                            EntityType.EXTERNAL_REFERENCE,
                            ["topic-selector", endpoint.id, topic_index],
                            "Kafka topic",
                            node,
                        ),
                        source=EntityRef(
                            id=endpoint.id, entity_type=endpoint.entity_type
                        ),
                        selector=SymbolSelector(qualified_name=resource.qualified_name),
                        reason="Deferred Kafka resource selector; cluster/environment are source configuration candidates, not runtime or cross-repository proof.",
                        certainty=Certainty.UNKNOWN,
                        evidence=self.evidence(node, "kafka.external-topic"),
                        coverage=CAPABILITY,
                    )
                )
            else:
                self.diagnostic(
                    node,
                    "DYNAMIC_TOPIC",
                    "Topic cannot be determined from a literal/final constant; no concrete topic is asserted.",
                )

    def generic_types(self, symbol: Symbol | None) -> tuple[str | None, str | None]:
        text = symbol.type_ref.name if symbol and symbol.type_ref else ""
        match = re.fullmatch(r"[^<]+<([^<>]+)>", text)
        args = [x.strip() for x in match[1].split(",")] if match else []
        return (args[-2], args[-1]) if len(args) == 2 else (None, None)

    def context(self, direction: str) -> dict[str, str]:
        context = {
            k: v
            for k, v in self.config.items()
            if not k.startswith(("producer.", "consumer."))
        }
        context.update(
            {
                k.removeprefix(direction + "."): v
                for k, v in self.config.items()
                if k.startswith(direction + ".")
            }
        )
        return context

    def collect(self) -> AdapterFileResult:
        if self.unit.source.file.path in self.collector.limited:
            return AdapterFileResult(
                analysis=FileAnalysis(
                    path=self.unit.source.file.path, dependencies=self.dependencies
                ),
                diagnostics=(
                    SourceDiagnostic(
                        severity="WARNING",
                        code="kafka.SOURCE_LIMIT",
                        message="Kafka pass exceeds 4 MiB/100000 AST nodes/depth 128 budget; Kafka facts suppressed.",
                    ),
                ),
            )
        if self.unit.result.diagnostics:
            return AdapterFileResult(
                analysis=FileAnalysis(
                    path=self.unit.source.file.path, dependencies=self.dependencies
                ),
                diagnostics=(
                    SourceDiagnostic(
                        severity="WARNING",
                        code="kafka.JAVA_PARSE_ERROR",
                        message="Kafka facts suppressed for malformed canonical Java AST.",
                    ),
                ),
            )
        for owner in self.unit.result.declared:
            if isinstance(owner, Symbol) and owner.symbol_kind == "CLASS":
                class_node = self.unit.extractor.symbol_nodes[owner.id]
                if tuple(self.unit.annotation(class_node, LISTENER)):
                    self.diagnostic(
                        class_node,
                        "CLASS_LISTENER_UNSUPPORTED",
                        "Class-level KafkaListener/KafkaHandler dispatch is not resolved.",
                    )
            if not isinstance(owner, Symbol) or owner.symbol_kind not in (
                "METHOD",
                "CONSTRUCTOR",
            ):
                continue
            method = self.unit.extractor.symbol_nodes[owner.id]
            for annotation in self.unit.annotation(method, LISTENER):
                args = arguments(annotation)
                override = self.context("consumer")
                for entry in (
                    self.collector.strings(
                        self.unit, args.get("properties"), owner.scope_id
                    )
                    if "properties" in args
                    else ()
                ):
                    if entry and "=" in entry:
                        name, value = entry.split("=", 1)
                        if name.strip() in CONFIG_KEYS:
                            override[name.strip()] = value.strip()
                    elif entry is None:
                        override.clear()
                if "groupId" in args:
                    group = self.collector.string(
                        self.unit, args["groupId"], owner.scope_id
                    )
                    if group:
                        override["group.id"] = group
                for key, attribute in (
                    ("id", "listener.id"),
                    ("clientIdPrefix", "client.id"),
                ):
                    value = self.collector.string(
                        self.unit, args.get(key), owner.scope_id
                    )
                    if value:
                        override[attribute] = value
                value_type = None
                parameters = method.child_by_field_name("parameters")
                params = list(parameters.named_children) if parameters else []
                key_type = None
                if len(params) == 1:
                    type_node = params[0].child_by_field_name("type")
                    if type_node:
                        text = java._text(type_node)
                        if self.unit.qualify(text) == CONSUMER_RECORD:
                            args_node = next(
                                (
                                    n
                                    for n in type_node.named_children
                                    if n.type == "type_arguments"
                                ),
                                None,
                            )
                            types = (
                                [java._text(n) for n in args_node.named_children]
                                if args_node
                                else []
                            )
                            if len(types) == 2:
                                key_type, value_type = types
                        else:
                            value_type = text
                topics = self.collector.strings(
                    self.unit, args.get("topics"), owner.scope_id
                )
                if "topicPattern" in args or "topicPartitions" in args:
                    self.diagnostic(
                        annotation,
                        "UNSUPPORTED_LISTENER_SELECTOR",
                        "Pattern/partition selectors are retained as partial; concrete topic is not guessed.",
                    )
                    topics = (None,)
                self.endpoint(
                    owner,
                    annotation,
                    "CONSUMER",
                    topics,
                    LISTENER,
                    override,
                    key_type,
                    value_type,
                    self.collector.string(
                        self.unit, args.get("containerFactory"), owner.scope_id
                    ),
                    proofs=(
                        *self.config_evidence,
                        self.proof(method, "kafka.handler-signature"),
                    ),
                )
            uncertain_config_flow = any(
                n.type
                in (
                    "if_statement",
                    "for_statement",
                    "enhanced_for_statement",
                    "while_statement",
                    "do_statement",
                    "switch_expression",
                    "switch_statement",
                    "try_statement",
                    "try_with_resources_statement",
                    "lambda_expression",
                    "class_declaration",
                    "interface_declaration",
                    "record_declaration",
                    "class_body",
                )
                for n in walk(method)
            )
            maps = {}
            map_proofs = {}
            client_configs = {}
            client_proofs = {}
            for node in walk(method):
                if node.type == "assignment_expression":
                    assigned = self.unit.resolve(node.child_by_field_name("left"))
                    if assigned:
                        maps.pop(assigned.id, None)
                        client_configs.pop(assigned.id, None)
                        client_proofs.pop(assigned.id, None)
                        map_proofs.pop(assigned.id, None)
                if node.type == "variable_declarator":
                    name = node.child_by_field_name("name")
                    symbol = self.unit.resolve(name)
                    value = node.child_by_field_name("value")
                    if (
                        symbol
                        and value
                        and value.type == "object_creation_expression"
                        and self.unit.qualify(
                            java._text(value.child_by_field_name("type"))
                        )
                        in ("java.util.Properties", "java.util.Map")
                    ):
                        maps[symbol.id] = {}
                        map_proofs[symbol.id] = []
                    if (
                        symbol
                        and value
                        and value.type == "object_creation_expression"
                        and self.unit.qualify(
                            java._text(value.child_by_field_name("type"))
                        )
                        in (PRODUCERS | CONSUMERS)
                    ):
                        constructor_args = value.child_by_field_name("arguments")
                        values = (
                            list(constructor_args.named_children)
                            if constructor_args
                            else []
                        )
                        config_symbol = self.unit.resolve(values[0]) if values else None
                        client_configs[symbol.id] = (
                            dict(maps.get(config_symbol.id, {}))
                            if config_symbol
                            else {}
                        )
                        client_proofs[symbol.id] = (
                            (*map_proofs.get(config_symbol.id, ()), node)
                            if config_symbol
                            else (node,)
                        )
                    if value and value.type == "identifier":
                        alias = self.unit.resolve(value)
                        if alias and alias.id in maps:
                            maps[alias.id].clear()
                            map_proofs[alias.id] = []
                if node.type != "method_invocation":
                    if (
                        node.type == "object_creation_expression"
                        and self.unit.qualify(
                            java._text(node.child_by_field_name("type"))
                        )
                        == NEW_TOPIC
                    ):
                        args_node = node.child_by_field_name("arguments")
                        args = list(args_node.named_children) if args_node else []
                        topic = self.collector.string(
                            self.unit, args[0] if args else None, owner.scope_id
                        )
                        self.endpoint(
                            owner,
                            node,
                            "DECLARATION",
                            (topic,),
                            NEW_TOPIC,
                            dict(self.config),
                        )
                    continue
                receiver_node = node.child_by_field_name("object")
                receiver = self.unit.resolve(receiver_node)
                method_name = java._text(node.child_by_field_name("name"))
                args_node = node.child_by_field_name("arguments")
                args = list(args_node.named_children) if args_node else []
                for argument in args:
                    escaped = self.unit.resolve(argument)
                    if (
                        escaped
                        and escaped.id in maps
                        and (receiver is None or receiver.id != escaped.id)
                    ):
                        maps[escaped.id].clear()
                        map_proofs[escaped.id] = []
                if receiver and receiver.id in maps:
                    if method_name == "put" and len(args) == 2:
                        name = self.collector.string(self.unit, args[0], owner.scope_id)
                        if name is None and args[0].type == "field_access":
                            config_owner = args[0].child_by_field_name("object")
                            if self.unit.qualify(java._text(config_owner)) in (
                                "org.apache.kafka.clients.producer.ProducerConfig",
                                "org.apache.kafka.clients.consumer.ConsumerConfig",
                            ):
                                name = CONFIG_CONSTANTS.get(
                                    java._text(args[0].child_by_field_name("field"))
                                )
                        value = self.collector.string(
                            self.unit, args[1], owner.scope_id
                        )
                        if args[1].type == "class_literal":
                            value = self.unit.qualify(
                                java._text(args[1]).removesuffix(".class")
                            )
                        # Branch-dependent values are not treated as an effective map.
                        parent = node.parent
                        conditional = False
                        while parent and parent.id != method.id:
                            conditional |= parent.type in (
                                "if_statement",
                                "for_statement",
                                "while_statement",
                                "switch_expression",
                                "try_statement",
                                "lambda_expression",
                            )
                            parent = parent.parent
                        if (
                            name
                            and value
                            and not conditional
                            and not uncertain_config_flow
                        ):
                            maps[receiver.id][name] = value
                            map_proofs[receiver.id].append(node)
                        else:
                            maps[receiver.id].clear()
                            map_proofs[receiver.id] = []
                    elif method_name not in ("get", "getProperty"):
                        maps[receiver.id].clear()
                        map_proofs[receiver.id] = []
                qualified = (
                    self.unit.qualify(receiver.type_ref.name)
                    if receiver and receiver.type_ref
                    else None
                )
                if qualified in self.collector.types:
                    continue
                if qualified in PRODUCERS and method_name == "send":
                    if qualified == TEMPLATE:
                        topic = self.collector.string(
                            self.unit, args[0] if args else None, owner.scope_id
                        )
                        context = self.context("producer")
                    else:
                        context = dict(client_configs.get(receiver.id, {}))
                        record = args[0] if args else None
                        if (
                            record
                            and record.type == "object_creation_expression"
                            and self.unit.qualify(
                                java._text(record.child_by_field_name("type"))
                            )
                            == RECORD
                        ):
                            record_args = record.child_by_field_name("arguments")
                            values = (
                                list(record_args.named_children) if record_args else []
                            )
                            topic = self.collector.string(
                                self.unit, values[0] if values else None, owner.scope_id
                            )
                        else:
                            topic = None
                    key_type, value_type = self.generic_types(receiver)
                    self.endpoint(
                        owner,
                        node,
                        "PRODUCER",
                        (topic,),
                        qualified + ".send",
                        context,
                        key_type,
                        value_type,
                        proofs=(
                            self.config_evidence
                            if qualified == TEMPLATE
                            else tuple(
                                self.proof(n, "kafka.client-configuration")
                                for n in client_proofs.get(receiver.id, ())
                            )
                        )
                        + (
                            self.proof(
                                self.unit.extractor.symbol_nodes[receiver.id],
                                "kafka.receiver-type",
                            ),
                        ),
                    )
                if qualified in CONSUMERS and method_name == "subscribe":
                    values = args[0] if args else None
                    topics = (None,)
                    if values and values.type == "method_invocation":
                        factory = java._text(values.child_by_field_name("object"))
                        name = java._text(values.child_by_field_name("name"))
                        if self.unit.qualify(factory) in (
                            "java.util.List",
                            "java.util.Arrays",
                            "java.util.Collections",
                        ) and name in ("of", "asList", "singletonList"):
                            items = values.child_by_field_name("arguments")
                            topics = (
                                tuple(
                                    self.collector.string(
                                        self.unit, item, owner.scope_id
                                    )
                                    for item in items.named_children
                                )
                                if items
                                else (None,)
                            )
                    key_type, value_type = self.generic_types(receiver)
                    self.endpoint(
                        owner,
                        node,
                        "CONSUMER",
                        topics,
                        qualified + ".subscribe",
                        dict(client_configs.get(receiver.id, {})),
                        key_type,
                        value_type,
                        proofs=tuple(
                            self.proof(n, "kafka.client-configuration")
                            for n in client_proofs.get(receiver.id, ())
                        )
                        + (
                            self.proof(
                                self.unit.extractor.symbol_nodes[receiver.id],
                                "kafka.receiver-type",
                            ),
                        ),
                    )
        return AdapterFileResult(
            analysis=FileAnalysis(
                path=self.unit.source.file.path,
                entities=tuple(self.entities),
                dependencies=self.dependencies,
            ),
            diagnostics=tuple(self.diagnostics),
        )
