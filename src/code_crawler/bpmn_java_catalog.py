"""BPMN binding facts collected from the canonical Java symbol extractor's AST."""

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from tree_sitter import Node

from code_crawler import java
from code_crawler.incremental import SourceInput
from code_crawler.java_calls import _erase, _modifiers
from code_crawler.java_symbols import JavaSymbolsResult
from code_crawler.jpa_catalog import arguments
from code_crawler.source_adapters import AdapterCatalog
from code_crawler.ucm import ContractModel, Evidence, SourceRange, Symbol, Text

CATALOG_KEY = "java.bpmn.handlers"
CATALOG_VERSION = "java.bpmn.handlers/1"
DELEGATES = {
    "camunda7": (
        "org.camunda.bpm.engine.delegate.JavaDelegate",
        "org.camunda.bpm.engine.delegate.DelegateExecution",
    ),
    "flowable": (
        "org.flowable.engine.delegate.JavaDelegate",
        "org.flowable.engine.delegate.DelegateExecution",
    ),
}
COMPONENTS = frozenset(
    (
        "org.springframework.stereotype.Component",
        "org.springframework.stereotype.Service",
        "javax.inject.Named",
        "jakarta.inject.Named",
    )
)
BEAN = "org.springframework.context.annotation.Bean"
SUBSCRIPTION = "org.camunda.bpm.client.spring.annotation.ExternalTaskSubscription"
EXTERNAL_HANDLER = "org.camunda.bpm.client.task.ExternalTaskHandler"
EXTERNAL_PARAMS = (
    "org.camunda.bpm.client.task.ExternalTask",
    "org.camunda.bpm.client.task.ExternalTaskService",
)
JOB_WORKERS = frozenset(
    (
        "io.camunda.zeebe.spring.client.annotation.JobWorker",
        "io.camunda.spring.client.annotation.JobWorker",
    )
)
VARIABLES = frozenset(
    (
        "io.camunda.zeebe.spring.client.annotation.Variable",
        "io.camunda.spring.client.annotation.Variable",
    )
)
KNOWN_TYPES = frozenset(
    (
        *(value for pair in DELEGATES.values() for value in pair),
        *COMPONENTS,
        BEAN,
        SUBSCRIPTION,
        EXTERNAL_HANDLER,
        *EXTERNAL_PARAMS,
        *JOB_WORKERS,
        *VARIABLES,
    )
)


class JavaVariableAccess(ContractModel):
    direction: Literal["READ", "WRITE"]
    name: Text | None = None
    evidence: Evidence


class JavaHandler(ContractModel):
    kind: Literal["CLASS", "BEAN", "WORKER"]
    engine: Literal["camunda7", "camunda8", "flowable"]
    selector: Text
    registration: Text
    symbol: Symbol
    evidence: tuple[Evidence, ...]
    variables: tuple[JavaVariableAccess, ...] = ()


class JavaBindingCatalog(AdapterCatalog):
    handlers: tuple[JavaHandler, ...] = ()
    failed_paths: tuple[Text, ...] = ()


@dataclass
class _Unit:
    source: SourceInput
    result: JavaSymbolsResult
    package: str
    imports: dict[str, list[str]]
    wildcards: tuple[str, ...]


@dataclass
class _Type:
    unit: _Unit
    symbol: Symbol
    node: Node


class _Collector:
    def __init__(
        self, sources: tuple[tuple[SourceInput, JavaSymbolsResult], ...]
    ) -> None:
        self.types: dict[str, list[_Type]] = defaultdict(list)
        self.by_key: dict[str, _Type] = {}
        self.methods: dict[str, list[tuple[Symbol, Node]]] = defaultdict(list)
        self.failed = []
        for source, result in sources:
            if result.diagnostics:
                self.failed.append(source.file.path)
                continue
            root = result._extractor.parsed._tree.root_node
            package = next(
                (
                    java._text(n.named_children[-1])
                    for n in root.named_children
                    if n.type == "package_declaration"
                ),
                "",
            )
            imports: dict[str, list[str]] = defaultdict(list)
            wildcards = []
            for node in root.named_children:
                if node.type != "import_declaration":
                    continue
                text = java._text(node)
                if match := re.fullmatch(r"import\s+([\w.$]+)\s*;", text):
                    imports[match[1].rsplit(".", 1)[-1]].append(match[1])
                elif match := re.fullmatch(r"import\s+([\w.$]+)\.\*\s*;", text):
                    wildcards.append(match[1])
            unit = _Unit(source, result, package, dict(imports), tuple(wildcards))
            for symbol in result.declared:
                if not isinstance(symbol, Symbol):
                    continue
                node = result._extractor.symbol_nodes[symbol.id]
                if symbol.symbol_kind == "CLASS" and symbol.logical_key.startswith(
                    "java:type:"
                ):
                    info = _Type(unit, symbol, node)
                    self.types[symbol.qualified_name].append(info)
                    self.by_key[symbol.logical_key] = info
                elif symbol.symbol_kind == "METHOD":
                    self.methods[symbol.owner_key].append((symbol, node))

    def qualify(self, name: str, owner: _Type) -> str | None:
        name = _erase(name)
        if name in ("void", "boolean", "int", "long"):
            return name
        known = self.types.keys() | KNOWN_TYPES
        if name in known:
            return name
        package_name = f"{owner.unit.package}.{name}".lstrip(".")
        if package_name in self.types:
            return package_name
        outer = owner.symbol.qualified_name
        while outer:
            if (nested := outer + "." + name) in self.types:
                return nested
            outer = outer.rpartition(".")[0]
        head, _, tail = name.partition(".")
        imported = owner.unit.imports.get(head, [])
        if imported:
            options = {item + ("." + tail if tail else "") for item in imported}
            return (
                next(iter(options)) if len(options) == 1 and options <= known else None
            )
        if len(owner.unit.wildcards) == 1:
            qualified = owner.unit.wildcards[0] + "." + name
            return qualified if qualified in known else None
        return None

    def annotations(self, node: Node, owner: _Type) -> tuple[tuple[str, Node], ...]:
        modifiers = next(
            (c for c in node.named_children if c.type == "modifiers"), None
        )
        found = []
        for child in modifiers.named_children if modifiers else ():
            if child.type in ("annotation", "marker_annotation"):
                name = self.qualify(
                    java._text(child.child_by_field_name("name")), owner
                )
                if name in KNOWN_TYPES and name not in self.types:
                    found.append((name, child))
        return tuple(found)

    def bases(self, owner: _Type) -> tuple[str, ...]:
        result = []
        for child in owner.node.named_children:
            if child.type not in (
                "superclass",
                "super_interfaces",
                "extends_interfaces",
            ):
                continue
            nodes = child.named_children
            if nodes and nodes[0].type == "type_list":
                nodes = nodes[0].named_children
            for node in nodes:
                if name := self.qualify(java._text(node), owner):
                    result.append(name)
        return tuple(result)

    def implements(
        self, owner: _Type, contract: str, seen: frozenset[str] = frozenset()
    ) -> bool:
        if owner.symbol.id in seen or len(seen) >= 64:
            return False
        for name in self.bases(owner):
            if name == contract:
                return True
            parents = self.types.get(name, ())
            if len(parents) == 1 and self.implements(
                parents[0], contract, seen | {owner.symbol.id}
            ):
                return True
        return False

    def execute(
        self,
        owner: _Type,
        parameters: tuple[str, ...],
        seen: frozenset[str] = frozenset(),
    ) -> tuple[Symbol, Node, _Type] | None:
        if owner.symbol.id in seen or len(seen) >= 64:
            return None
        methods = []
        for symbol, node in self.methods.get(owner.symbol.logical_key, ()):
            if symbol.name != "execute" or symbol.signature is None:
                continue
            actual = tuple(
                self.qualify(t.name, owner) for t in symbol.signature.parameter_types
            )
            if (
                actual == parameters
                and symbol.signature.return_type is not None
                and symbol.signature.return_type.name == "void"
                and "public" in _modifiers(node)
                and not {"static", "abstract"} & _modifiers(node)
                and node.child_by_field_name("body") is not None
            ):
                methods.append((symbol, node, owner))
        if methods:
            return methods[0] if len(methods) == 1 else None
        for base in self.bases(owner):
            parents = self.types.get(base, ())
            if len(parents) == 1 and (
                found := self.execute(parents[0], parameters, seen | {owner.symbol.id})
            ):
                methods.append(found)
        return methods[0] if len(methods) == 1 else None

    def evidence(self, owner: _Type, node: Node, rule: str) -> Evidence:
        return Evidence(
            source_range=SourceRange(
                source_file_id=owner.unit.source.file.id,
                start=java._span(node).start,
                end=java._span(node).end,
            ),
            analyzer="bpmn.java",
            analyzer_version=CATALOG_VERSION,
            rule=rule,
            description="Declared Java syntax; runtime registration and execution are not asserted.",
        )

    def variables(self, owner: _Type, method: Node) -> tuple[JavaVariableAccess, ...]:
        receivers = {}
        result = []
        parameters = method.child_by_field_name("parameters")
        for param in parameters.named_children if parameters else ():
            type_node, name_node = (
                param.child_by_field_name("type"),
                param.child_by_field_name("name"),
            )
            if type_node is None or name_node is None:
                continue
            receiver = java._text(name_node)
            qualified = self.qualify(java._text(type_node), owner)
            if qualified in {pair[1] for pair in DELEGATES.values()} | {
                EXTERNAL_PARAMS[0]
            }:
                receivers[receiver] = qualified
            for annotation, node in self.annotations(param, owner):
                if annotation in VARIABLES:
                    args = arguments(node)
                    names = _names(args, ("name", "value"), receiver)
                    result.append(
                        JavaVariableAccess(
                            direction="READ",
                            name=names[0] if len(names) == 1 else None,
                            evidence=self.evidence(owner, node, "job.variable"),
                        )
                    )
        pending = [method.child_by_field_name("body")]
        while pending:
            node = pending.pop()
            if node is None or node.type in (
                "lambda_expression",
                "class_declaration",
                "anonymous_class_body",
                "method_declaration",
                "constructor_declaration",
                "class_body",
            ):
                continue
            if node.type == "method_invocation":
                obj, name = (
                    node.child_by_field_name("object"),
                    java._text(node.child_by_field_name("name")),
                )
                receiver = (
                    java._text(obj)
                    if obj is not None and obj.type == "identifier"
                    else None
                )
                params = node.child_by_field_name("arguments")
                args = params.named_children if params else ()
                reads = name in ("getVariable", "getVariableLocal") and len(args) == 1
                writes = name in ("setVariable", "setVariableLocal") and len(args) == 2
                if (
                    receiver in receivers
                    and (reads or writes)
                    and (reads or receivers[receiver] != EXTERNAL_PARAMS[0])
                ):
                    result.append(
                        JavaVariableAccess(
                            direction="READ" if reads else "WRITE",
                            name=_string(args[0]) or None,
                            evidence=self.evidence(
                                owner, node, "delegate.variable." + name
                            ),
                        )
                    )
            pending.extend(reversed(node.named_children))
        return tuple(result)

    def contract_evidence(
        self, owner: _Type, seen: frozenset[str] = frozenset()
    ) -> tuple[Evidence, ...]:
        if owner.symbol.id in seen or len(seen) >= 64:
            return ()
        proof = [self.evidence(owner, owner.node, "delegate.contract")]
        for name in self.bases(owner):
            parents = self.types.get(name, ())
            if len(parents) == 1:
                proof.extend(
                    self.contract_evidence(parents[0], seen | {owner.symbol.id})
                )
        return tuple(proof)

    def collect(self) -> tuple[JavaHandler, ...]:
        declared = []
        for owners in self.types.values():
            for owner in owners:
                if owner.node.type not in (
                    "class_declaration",
                    "record_declaration",
                ) or "abstract" in _modifiers(owner.node):
                    continue
                for engine, (contract, param) in DELEGATES.items():
                    method = self.execute(owner, (param,))
                    if not self.implements(owner, contract) or method is None:
                        continue
                    symbol, node, defining = method
                    declared.append(
                        JavaHandler(
                            kind="CLASS",
                            engine=engine,
                            selector=owner.symbol.qualified_name,
                            registration=owner.symbol.id,
                            symbol=symbol,
                            evidence=(
                                *self.contract_evidence(owner),
                                self.evidence(defining, node, "delegate.execute"),
                            ),
                            variables=self.variables(defining, node),
                        )
                    )
        result = list(declared)
        for owners in self.types.values():
            for owner in owners:
                annotations = self.annotations(owner.node, owner)
                default = owner.symbol.name
                default = (
                    default
                    if len(default) > 1
                    and default[0].isupper()
                    and default[1].isupper()
                    else default[:1].lower() + default[1:]
                )
                for annotation, node in annotations:
                    if annotation in COMPONENTS:
                        for name in _names(arguments(node), ("value", "name"), default):
                            result.extend(
                                JavaHandler(
                                    **{
                                        **handler.model_dump(),
                                        "kind": "BEAN",
                                        "selector": name,
                                        "registration": owner.symbol.id
                                        + ":"
                                        + str(node.start_byte),
                                        "evidence": (
                                            *handler.evidence,
                                            self.evidence(owner, node, "spring.bean"),
                                        ),
                                    }
                                )
                                for handler in declared
                                if handler.registration == owner.symbol.id
                            )
                    if (
                        annotation == SUBSCRIPTION
                        and self.implements(owner, EXTERNAL_HANDLER)
                        and owner.node.type
                        in ("class_declaration", "record_declaration")
                        and "abstract" not in _modifiers(owner.node)
                    ):
                        method = self.execute(owner, EXTERNAL_PARAMS)
                        if method:
                            symbol, body, defining = method
                            for topic in _names(
                                arguments(node), ("value", "topicName")
                            ):
                                result.append(
                                    JavaHandler(
                                        kind="WORKER",
                                        engine="camunda7",
                                        selector=topic,
                                        registration=owner.symbol.id,
                                        symbol=symbol,
                                        evidence=(
                                            self.evidence(
                                                owner, node, "external.subscription"
                                            ),
                                            self.evidence(
                                                defining, body, "external.execute"
                                            ),
                                        ),
                                        variables=self.variables(defining, body),
                                    )
                                )
                for symbol, method in self.methods.get(owner.symbol.logical_key, ()):
                    for annotation, node in self.annotations(method, owner):
                        if (
                            annotation in JOB_WORKERS
                            and owner.node.type
                            in ("class_declaration", "record_declaration")
                            and "abstract" not in _modifiers(owner.node)
                            and not (
                                (enabled := arguments(node).get("enabled")) is not None
                                and java._text(enabled) == "false"
                            )
                            and not {"static", "abstract"} & _modifiers(method)
                            and method.child_by_field_name("body") is not None
                        ):
                            for topic in _names(arguments(node), ("type",)):
                                result.append(
                                    JavaHandler(
                                        kind="WORKER",
                                        engine="camunda8",
                                        selector=topic,
                                        registration=symbol.id,
                                        symbol=symbol,
                                        evidence=(
                                            self.evidence(owner, node, "job.worker"),
                                            self.evidence(owner, method, "job.method"),
                                        ),
                                        variables=self.variables(owner, method),
                                    )
                                )
                        if (
                            annotation == BEAN
                            and symbol.signature
                            and symbol.signature.return_type
                        ):
                            target = self.qualify(
                                symbol.signature.return_type.name, owner
                            )
                            for name in _names(
                                arguments(node), ("value", "name"), symbol.name
                            ):
                                for handler in declared:
                                    if (
                                        target == handler.selector
                                        or target == DELEGATES[handler.engine][0]
                                    ):
                                        result.append(
                                            JavaHandler(
                                                **{
                                                    **handler.model_dump(),
                                                    "kind": "BEAN",
                                                    "selector": name,
                                                    "registration": symbol.id,
                                                    "evidence": (
                                                        *handler.evidence,
                                                        self.evidence(
                                                            owner,
                                                            node,
                                                            "spring.factory",
                                                        ),
                                                    ),
                                                }
                                            )
                                        )
        return tuple(
            sorted(
                result,
                key=lambda h: (
                    h.kind,
                    h.engine,
                    h.selector,
                    h.symbol.id,
                    h.registration,
                ),
            )
        )


def _string(node: Node | None) -> str | None:
    if node is None or node.type != "string_literal":
        return None
    try:
        value = java._literal(node)
        return value if "\0" not in value else None
    except ValueError:
        return None


def _names(
    args: dict[str, Node], keys: tuple[str, ...], default: str | None = None
) -> tuple[str, ...]:
    present = [args[key] for key in keys if key in args]
    if not present:
        return (default,) if default else ()
    if len(present) != 1:
        return ()
    node = present[0]
    nodes = (
        node.named_children
        if node.type == "element_value_array_initializer"
        else (node,)
    )
    values = [_string(item) for item in nodes]
    return (
        tuple(dict.fromkeys(values))
        if values and all(value and value.strip() for value in values)
        else ()
    )


def java_binding_catalog(
    sources: tuple[tuple[SourceInput, JavaSymbolsResult], ...],
    profile: str,
) -> JavaBindingCatalog:
    """Export immutable binding declarations from already parsed canonical Java ASTs."""
    sources = tuple(sorted(sources, key=lambda pair: pair[0].file.path))
    collector = _Collector(sources)
    payload = {
        "key": CATALOG_KEY,
        "source_files": tuple(source.file for source, _ in sources),
        "handlers": collector.collect(),
        "failed_paths": tuple(sorted(collector.failed)),
    }
    provisional = JavaBindingCatalog(version=CATALOG_VERSION, **payload)
    digest = hashlib.sha256(
        json.dumps(
            [profile, provisional.model_dump(mode="json")],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return JavaBindingCatalog(version=CATALOG_VERSION + ":" + digest, **payload)
