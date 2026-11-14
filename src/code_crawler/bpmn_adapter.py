"""Safe, captured-byte BPMN 2.0 producer; never evaluates engine expressions."""

import asyncio
import json
from bisect import bisect_right
from dataclasses import dataclass, field
from xml.parsers import expat

from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.source_adapters import (
    AdapterDescriptor,
    AdapterFileResult,
    PreparedAdapter,
    SourceRoute,
)
from code_crawler.ucm import (
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    Position,
    Relation,
    RelationKind,
    Resolution,
    SourceDiagnostic,
    SourceRange,
    Symbol,
    SymbolSelector,
    TypeRef,
    Value,
    logical_id,
)

BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CAMUNDA = "http://camunda.org/schema/1.0/bpmn"
ZEEBE = "http://camunda.org/schema/zeebe/1.0"
VERSION = "bpmn/1"
MAX_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 128
MAX_ELEMENTS = 20000
CAPABILITY = Coverage(
    capability="bpmn.schema",
    analyzer_version=VERSION,
    status="PARTIAL",
    reasons=("Engine extensions and expressions are preserved without evaluation.",),
)
FLOW_NODES = frozenset(
    [
        "startEvent",
        "endEvent",
        "intermediateCatchEvent",
        "intermediateThrowEvent",
        "boundaryEvent",
        "serviceTask",
        "userTask",
        "task",
        "scriptTask",
        "manualTask",
        "businessRuleTask",
        "sendTask",
        "receiveTask",
        "callActivity",
        "subProcess",
        "transaction",
        "exclusiveGateway",
        "inclusiveGateway",
        "parallelGateway",
        "eventBasedGateway",
        "complexGateway",
    ]
)


def _qname(name: str) -> str:
    return "{" + name if "}" in name else name


@dataclass
class _Node:
    tag: str
    attributes: dict[str, str]
    parent: int | None
    start: int
    end: int
    empty: bool
    text: list[str] = field(default_factory=list)


def _tag_end(content: bytes, start: int) -> int:
    quote = None
    for offset in range(start, len(content)):
        char = content[offset]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in (34, 39):
            quote = char
        elif char == 62:
            return offset + 1
    raise ValueError("Unterminated XML tag")


def _parse(content: bytes) -> list[_Node]:
    if len(content) > MAX_BYTES:
        raise ValueError("XML exceeds 8 MiB limit")
    content.decode("utf-8-sig")
    parser = expat.ParserCreate(namespace_separator="}")
    nodes: list[_Node] = []
    stack: list[int] = []

    def reject(*args: object) -> None:
        raise ValueError("DTD and entity declarations/references are forbidden")

    def declaration(version: str, encoding: str | None, standalone: int) -> None:
        if encoding and encoding.lower().replace("-", "") != "utf8":
            raise ValueError("Only UTF-8 XML is supported")

    def start(tag: str, attributes: dict[str, str]) -> None:
        if len(stack) >= MAX_DEPTH or len(nodes) >= MAX_ELEMENTS:
            raise ValueError("XML depth/element limit exceeded")
        offset = parser.CurrentByteIndex
        end = _tag_end(content, offset)
        nodes.append(
            _Node(
                _qname(tag),
                {_qname(k): v for k, v in attributes.items()},
                stack[-1] if stack else None,
                offset,
                end,
                content[offset:end].rstrip().endswith(b"/>"),
            )
        )
        stack.append(len(nodes) - 1)

    def end(tag: str) -> None:
        node = nodes[stack.pop()]
        if not node.empty:
            node.end = _tag_end(content, parser.CurrentByteIndex)

    def text(value: str) -> None:
        if stack:
            nodes[stack[-1]].text.append(value)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    parser.XmlDeclHandler = declaration
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(content, True)
    return nodes


def analyze_bpmn(source: SourceInput) -> AdapterFileResult:
    """Extract local XML facts and deferred selectors from one captured UTF-8 file."""
    diagnostics: list[SourceDiagnostic] = []

    def diagnostic(
        code: str, message: str, location: SourceRange | None = None
    ) -> None:
        diagnostics.append(
            SourceDiagnostic(
                severity="ERROR",
                code="bpmn." + code,
                message=message,
                source_range=location,
            )
        )

    def result(entities: tuple = (), unsupported: bool = False) -> AdapterFileResult:
        return AdapterFileResult(
            analysis=FileAnalysis(path=source.file.path, entities=entities),
            diagnostics=tuple(diagnostics),
            capabilities=(
                Coverage(
                    capability=CAPABILITY.capability,
                    analyzer_version=VERSION,
                    status="UNSUPPORTED",
                    reasons=("XML root is not BPMN 2.0 definitions.",),
                ),
            )
            if unsupported
            else (CAPABILITY,),
        )

    try:
        nodes = _parse(source.content)
    except (ValueError, expat.ExpatError, UnicodeError) as error:
        diagnostic("INVALID_XML", str(error))
        return result()
    if not nodes or nodes[0].tag != f"{{{BPMN}}}definitions":
        return result(unsupported=True)
    starts = [0] + [i + 1 for i, char in enumerate(source.content) if char == 10]

    def position(offset: int) -> Position:
        line = bisect_right(starts, offset)
        return Position(line=line, byte_column=offset - starts[line - 1])

    def location(node: _Node) -> SourceRange:
        return SourceRange(
            source_file_id=source.file.id,
            start=position(node.start),
            end=position(node.end),
        )

    repo = source.file.repository_id

    def base(kind: EntityType, key: object, name: str, node: _Node) -> dict:
        logical_key = json.dumps(["bpmn", source.file.path, key], separators=(",", ":"))
        return {
            "repository_id": repo,
            "logical_key": logical_key,
            "id": logical_id(repo, kind, logical_key),
            "name": name,
            "source_range": location(node),
        }

    ids: dict[str, int] = {}
    keys = []
    child_counts: dict[int | None, int] = {}
    for index, node in enumerate(nodes):
        count = child_counts.get(node.parent, 0)
        child_counts[node.parent] = count + 1
        xml_id = node.attributes.get("id")
        if xml_id:
            if xml_id in ids:
                diagnostic(
                    "DUPLICATE_ID", "Duplicate XML ID: " + xml_id, location(node)
                )
                return result()
            ids[xml_id] = index
        keys.append(
            ["id", xml_id]
            if xml_id
            else [
                "child",
                keys[node.parent] if node.parent is not None else "root",
                count,
            ]
        )
    symbols = [
        Symbol(
            **base(
                EntityType.SYMBOL,
                keys[i],
                next(
                    (
                        value
                        for value in (
                            node.attributes.get("name", ""),
                            node.attributes.get("id", ""),
                        )
                        if value.strip()
                    ),
                    node.tag,
                ),
                node,
            ),
            symbol_kind="BPMN_ELEMENT",
            qualified_name=node.tag,
            type_ref=TypeRef(name=node.tag),
        )
        for i, node in enumerate(nodes)
    ]
    entities = list(symbols)

    def ref(entity: Symbol | Value) -> EntityRef:
        return EntityRef(id=entity.id, entity_type=entity.entity_type)

    def evidence(node: _Node, rule: str) -> tuple[Evidence, ...]:
        return (
            Evidence(
                source_range=location(node),
                analyzer="bpmn",
                analyzer_version=VERSION,
                rule=rule,
                description="Explicit BPMN XML syntax; no execution inferred.",
            ),
        )

    def link(
        kind: RelationKind, origin: Symbol, target: Symbol | Value, node: _Node
    ) -> None:
        entities.append(
            Relation(
                **base(
                    EntityType.RELATION,
                    [kind.value, origin.id, target.id],
                    kind.value,
                    node,
                ),
                relation_kind=kind,
                source=ref(origin),
                resolution=Resolution(status="RESOLVED", target=ref(target)),
                certainty=Certainty.STATIC_PROVEN,
                evidence=evidence(node, kind.value),
                coverage=CAPABILITY,
            )
        )

    def external(symbol: Symbol, role: str, value: str, node: _Node) -> None:
        if not value.strip():
            return
        entities.append(
            ExternalReference(
                **base(
                    EntityType.EXTERNAL_REFERENCE, [symbol.id, role, value], role, node
                ),
                source=ref(symbol),
                selector=SymbolSelector(qualified_name=f"bpmn.{role}::{value}"),
                reason="Deferred engine selector; no external repository is read.",
                evidence=evidence(node, "bpmn.external." + role),
                certainty=Certainty.UNKNOWN
                if any(c in value for c in ("${", "#{", "="))
                else Certainty.STATIC_PROVEN,
                coverage=CAPABILITY,
            )
        )

    def container(index: int) -> int | None:
        parent = nodes[index].parent
        while parent is not None:
            if nodes[parent].tag in (
                f"{{{BPMN}}}process",
                f"{{{BPMN}}}subProcess",
                f"{{{BPMN}}}transaction",
            ):
                return parent
            parent = nodes[parent].parent
        return None

    for index, (node, symbol) in enumerate(zip(nodes, symbols)):
        if node.parent is not None:
            link(RelationKind.CONTAINS, symbols[node.parent], symbol, node)
        for name, value in (
            *sorted(node.attributes.items()),
            ("#text", "".join(node.text)),
        ):
            if name == "#text" and not value.strip():
                continue
            literal = Value(
                **base(EntityType.VALUE, [symbol.id, name], name, node),
                value_kind="LITERAL",
                literal=value,
            )
            entities.append(literal)
            link(
                RelationKind.BPMN_TEXT
                if name == "#text"
                else RelationKind.BPMN_ATTRIBUTE,
                symbol,
                literal,
                node,
            )
        if node.tag == f"{{{BPMN}}}sequenceFlow":
            endpoints = [
                ids.get(node.attributes.get(attr, ""))
                for attr in ("sourceRef", "targetRef")
            ]
            if any(
                target is None
                or container(target) != container(index)
                or container(index) is None
                or nodes[target].tag not in {f"{{{BPMN}}}{name}" for name in FLOW_NODES}
                for target in endpoints
            ):
                diagnostic(
                    "INVALID_FLOW",
                    "Missing, invalid or out-of-scope flow endpoint.",
                    location(node),
                )
            else:
                for kind, target in zip(
                    (RelationKind.BPMN_FLOW_SOURCE, RelationKind.BPMN_FLOW_TARGET),
                    endpoints,
                ):
                    link(kind, symbol, symbols[target], node)
        if node.tag == f"{{{BPMN}}}callActivity" and (
            called := node.attributes.get("calledElement")
        ):
            target = ids.get(called)
            if target is not None and nodes[target].tag == f"{{{BPMN}}}process":
                link(RelationKind.BPMN_CALLS_PROCESS, symbol, symbols[target], node)
            else:
                external(symbol, "process", called, node)
        if node.tag == f"{{{BPMN}}}serviceTask":
            if worker := node.attributes.get(f"{{{CAMUNDA}}}topic"):
                external(symbol, "worker", worker, node)
            for attr in ("class", "delegateExpression", "expression"):
                if value := node.attributes.get(f"{{{CAMUNDA}}}{attr}"):
                    external(symbol, attr, value, node)
        if node.tag == f"{{{ZEEBE}}}taskDefinition" and (
            worker := node.attributes.get("type")
        ):
            external(symbol, "worker", worker, node)
    return result(tuple(entities))


@dataclass(frozen=True)
class BpmnSourceAdapter:
    @property
    def descriptor(self) -> AdapterDescriptor:
        return AdapterDescriptor(
            key="bpmn",
            version=VERSION,
            routes=tuple(
                SourceRoute(suffix=suffix, language="bpmn")
                for suffix in (".bpmn", ".bpmn20.xml", ".xml")
            ),
            capabilities=(CAPABILITY,),
            entity_types=(
                EntityType.SYMBOL,
                EntityType.VALUE,
                EntityType.RELATION,
                EntityType.EXTERNAL_REFERENCE,
            ),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        return _PreparedBpmn()


@dataclass(frozen=True)
class _PreparedBpmn:
    analysis_version: str = VERSION

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        return await asyncio.to_thread(
            lambda: tuple(analyze_bpmn(source) for source in sources)
        )
