import asyncio
import hashlib
from uuid import UUID

import pytest

from code_crawler.bpmn_adapter import (
    BPMN,
    MAX_BYTES,
    BpmnSourceAdapter,
    analyze_bpmn,
)
from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.ucm import (
    EntityType,
    ExternalReference,
    Relation,
    RelationKind,
    SourceAnalysis,
    SourceFile,
    Symbol,
    Value,
    logical_id,
)

REPO = "00000000-0000-0000-0000-000000000001"


def source(
    text: str | bytes, path: str = "process.bpmn", repo: str = REPO
) -> SourceInput:
    content = text.encode() if isinstance(text, str) else text
    return SourceInput(
        file=SourceFile(
            repository_id=repo,
            logical_key=path,
            id=logical_id(repo, EntityType.SOURCE_FILE, path),
            name=path,
            path=path,
            language="bpmn",
            content_sha256=hashlib.sha256(content).hexdigest(),
        ),
        content=content,
    )


def document(body: str) -> str:
    return f'''<b:definitions xmlns:b="{BPMN}" xmlns:c="http://camunda.org/schema/1.0/bpmn"
 xmlns:z="http://camunda.org/schema/zeebe/1.0" xmlns:x="urn:custom">
 <b:process id="p">{body}</b:process></b:definitions>'''


@pytest.fixture
def bpmn_xml() -> str:
    return document("""
 <b:startEvent id="start"/>
 <b:exclusiveGateway id="choice" name="Выбор"/>
 <b:serviceTask id="work" c:type="external" c:topic="charge">
   <b:extensionElements><z:taskDefinition type="payment"/>
     <c:inputOutput><c:inputParameter name="amount">${order.total}</c:inputParameter>
     <c:outputParameter name="result">${result}</c:outputParameter></c:inputOutput>
     <x:hint enabled="yes">opaque</x:hint>
   </b:extensionElements>
 </b:serviceTask>
 <b:userTask id="review"/>
 <b:endEvent id="done"/>
 <b:property id="variable" name="order"/>
 <b:sequenceFlow id="f1" sourceRef="choice" targetRef="work">
   <b:conditionExpression><![CDATA[${amount > 0}]]></b:conditionExpression>
 </b:sequenceFlow>
 <b:sequenceFlow id="f2" sourceRef="choice" targetRef="review">
   <b:conditionExpression>${amount &lt;= 0}</b:conditionExpression>
 </b:sequenceFlow>
 <b:subProcess id="nested"><b:startEvent id="inner"/></b:subProcess>
 <b:callActivity id="remote" calledElement="other-process"/>
 """)


def test_gateway_guards_extensions_and_external_workers(bpmn_xml: str) -> None:
    captured = source(bpmn_xml)

    async def run():
        prepared = await AdapterRegistry((BpmnSourceAdapter(),)).prepare((captured,))
        return (await prepared((captured,)))[0]

    analysis = asyncio.run(run())
    UcmBatch(repository_id=UUID(REPO), entities=(captured.file, *analysis.entities))
    entities = {e.id: e for e in analysis.entities}
    flows = [
        e
        for e in entities.values()
        if isinstance(e, Relation)
        and e.relation_kind
        in (RelationKind.BPMN_FLOW_SOURCE, RelationKind.BPMN_FLOW_TARGET)
    ]
    assert len(flows) == 4
    assert {entities[e.source.id].name for e in flows} == {"f1", "f2"}
    assert {entities[e.resolution.target.id].name for e in flows} == {
        "Выбор",
        "work",
        "review",
    }
    literals = {e.literal for e in entities.values() if isinstance(e, Value)}
    assert {
        "${amount > 0}",
        "${amount <= 0}",
        "${order.total}",
        "${result}",
        "opaque",
        "yes",
    } <= literals
    externals = [e for e in entities.values() if isinstance(e, ExternalReference)]
    assert {e.selector.qualified_name for e in externals} == {
        "bpmn.worker::charge",
        "bpmn.worker::payment",
        "bpmn.process::other-process",
    }
    assert all(e.resolution == "UNRESOLVED" for e in externals)
    report = next(e for e in entities.values() if isinstance(e, SourceAnalysis))
    assert not any(d.severity == "ERROR" for d in report.diagnostics)
    assert report.capabilities[0].status == "PARTIAL"
    # Every claimed span is a UTF-8 slice of the captured XML, including non-ASCII names.
    lines = captured.content.splitlines(keepends=True)
    for entity in entities.values():
        if entity.source_range:
            loc = entity.source_range
            begin = sum(map(len, lines[: loc.start.line - 1])) + loc.start.byte_column
            end = sum(map(len, lines[: loc.end.line - 1])) + loc.end.byte_column
            span = captured.content[begin:end].decode()
            assert span.startswith("<") and span.endswith(">")


@pytest.mark.parametrize(
    "body",
    [
        '<b:sequenceFlow id="f" sourceRef="missing" targetRef="a"/><b:task id="a"/>',
        (
            '<b:subProcess id="sub"><b:task id="a"/></b:subProcess><b:task id="b"/>'
            '<b:sequenceFlow id="f" sourceRef="a" targetRef="b"/>'
        ),
        '<b:property id="a"/><b:task id="b"/><b:sequenceFlow id="f" sourceRef="a" targetRef="b"/>',
    ],
)
def test_invalid_flows_have_no_false_links(body: str) -> None:
    result = analyze_bpmn(source(document(body)))
    assert result.diagnostics[0].code == "bpmn.INVALID_FLOW"
    assert not any(
        isinstance(e, Relation)
        and e.relation_kind
        in (RelationKind.BPMN_FLOW_SOURCE, RelationKind.BPMN_FLOW_TARGET)
        for e in result.analysis.entities
    )


@pytest.mark.parametrize(
    "payload",
    [
        (
            '<!DOCTYPE definitions [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            f'<definitions xmlns="{BPMN}">&x;</definitions>'
        ),
        (
            '<!DOCTYPE definitions SYSTEM "https://example.invalid/evil.dtd">'
            f'<definitions xmlns="{BPMN}"/>'
        ),
        (
            '<!DOCTYPE definitions [<!ENTITY x "expanded">]>'
            f'<definitions xmlns="{BPMN}">&x;</definitions>'
        ),
        document('<b:task id="a"/>')[:-15],
        b"\xff",
        document("<b:task/>").encode("utf-16-le"),
        document("<b:task/>").encode("utf-16-be"),
        '<?xml version="1.0" encoding="iso-8859-1"?><definitions/>',
        document("<b:subProcess>" * 129 + "</b:subProcess>" * 129),
        document("<b:task/>" * 20001),
        b" " * (MAX_BYTES + 1),
    ],
)
def test_unsafe_malformed_and_bounded_xml_has_diagnostics_only(
    payload: str | bytes,
) -> None:
    result = analyze_bpmn(source(payload))
    assert result.diagnostics[0].code == "bpmn.INVALID_XML"
    assert not result.analysis.entities
    assert result.capabilities[0].status == "PARTIAL"


def test_duplicate_ids_cannot_resolve_arbitrarily() -> None:
    result = analyze_bpmn(source(document('<b:task id="x"/><b:task id="x"/>')))
    assert result.diagnostics[0].code == "bpmn.DUPLICATE_ID"
    assert not result.analysis.entities


def test_local_process_resolution_and_foreign_namespace_not_interpreted() -> None:
    xml = f'''<definitions xmlns="{BPMN}" xmlns:x="urn:custom">
      <process id="p"><callActivity id="call" calledElement="q"/>
      <x:sequenceFlow sourceRef="bad" targetRef="bad"/></process><process id="q"/>
    </definitions>'''
    result = analyze_bpmn(source(xml))
    assert not result.diagnostics
    assert (
        sum(
            isinstance(e, Relation)
            and e.relation_kind == RelationKind.BPMN_CALLS_PROCESS
            for e in result.analysis.entities
        )
        == 1
    )
    assert not any(isinstance(e, ExternalReference) for e in result.analysis.entities)


def test_routing_unsupported_xml_and_repository_path_identity(bpmn_xml: str) -> None:
    registry = AdapterRegistry((BpmnSourceAdapter(),))
    for path in ("a.bpmn", "a.bpmn20.xml", "a.xml"):
        assert registry.route(path).key == "bpmn"
    assert registry.route("a.txt") is None
    assert (
        analyze_bpmn(source("<root/>", "unrelated.xml")).capabilities[0].status
        == "UNSUPPORTED"
    )
    first = analyze_bpmn(source(bpmn_xml)).analysis.entities
    assert first == analyze_bpmn(source(bpmn_xml)).analysis.entities
    assert {e.id for e in first}.isdisjoint(
        e.id
        for e in analyze_bpmn(
            source(bpmn_xml, repo="00000000-0000-0000-0000-000000000002")
        ).analysis.entities
    )
    assert {e.id for e in first}.isdisjoint(
        e.id
        for e in analyze_bpmn(source(bpmn_xml, path="other.bpmn")).analysis.entities
    )
    # ID-bearing symbols retain identity across unrelated insertions.
    changed = analyze_bpmn(
        source(bpmn_xml.replace("<b:startEvent", '<b:task id="new"/><b:startEvent', 1))
    )
    before = {e.name: e.id for e in first if isinstance(e, Symbol)}
    after = {e.name: e.id for e in changed.analysis.entities if isinstance(e, Symbol)}
    assert before["Выбор"] == after["Выбор"]


def test_external_entities_never_open_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins
    import socket
    from pathlib import Path

    captured = source(
        '<!DOCTYPE definitions [<!ENTITY secret SYSTEM "file:///private/sentinel">]>'
        f'<definitions xmlns="{BPMN}">&secret;</definitions>'
    )

    def forbidden(*args, **kwargs):
        pytest.fail("XML parser attempted filesystem or network access")

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", forbidden)
        patch.setattr(Path, "open", forbidden)
        patch.setattr(socket, "socket", forbidden)
        parsed = analyze_bpmn(captured)
    assert not parsed.analysis.entities
    assert parsed.diagnostics[0].code == "bpmn.INVALID_XML"


def test_dynamic_engine_selectors_remain_unknown() -> None:
    from code_crawler.ucm import Certainty

    result = analyze_bpmn(
        source(
            document(
                '<b:serviceTask id="worker" c:topic="${workerType}" '
                'c:delegateExpression="${delegate}"/>'
                '<b:callActivity id="call" calledElement="${processName}"/>'
            )
        )
    )
    external = [e for e in result.analysis.entities if isinstance(e, ExternalReference)]
    assert len(external) == 3
    assert all(e.certainty == Certainty.UNKNOWN for e in external)
    assert all(e.resolution == "UNRESOLVED" for e in external)


def test_default_namespace_bom_crlf_and_quoted_tag_end_ranges() -> None:
    xml = (
        "\ufeff"
        + f'<definitions xmlns="{BPMN}">\r\n<process id="p">'
        + ('<userTask id="t" name="a > b"/>\r\n</process></definitions>')
    )
    result = analyze_bpmn(source(xml))
    assert not result.diagnostics
    task = next(
        e
        for e in result.analysis.entities
        if isinstance(e, Symbol) and e.name == "a > b"
    )
    assert task.source_range.start.line == 2
    assert task.source_range.start.byte_column == len('<process id="p">')
    assert task.source_range.end.byte_column == len(
        '<process id="p"><userTask id="t" name="a > b"/>'
    )


def test_blank_labels_preserve_attributes_without_failing_ingestion() -> None:
    result = analyze_bpmn(source(document('<b:userTask id="task" name="  "/>')))
    assert not result.diagnostics
    assert any(
        isinstance(e, Symbol) and e.name == "task" for e in result.analysis.entities
    )
    assert any(
        isinstance(e, Value) and e.name == "name" and e.literal == "  "
        for e in result.analysis.entities
    )
