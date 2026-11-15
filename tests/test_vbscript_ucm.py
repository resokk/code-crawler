import hashlib

import pytest
from test_source_adapters import REPO, run, source

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.source_adapters import AdapterError, AdapterRegistry
from code_crawler.ucm import (
    DataAccess,
    ExternalReference,
    Relation,
    RelationKind,
    SourceAnalysis,
    SqlConstruction,
    SqlExecute,
    SqlStatement,
    Symbol,
)
from code_crawler.vbscript_adapter import VbscriptSourceAdapter
from code_crawler.vbscript_parse import parse_vbscript


def facts(text, path="A.vbs", dialect="postgres"):
    src = source(path, text, "vbscript")
    _, analyses = run(
        AdapterRegistry((VbscriptSourceAdapter(dialect=dialect),)), (src,)
    )
    return UcmBatch(
        repository_id=REPO, entities=(src.file, *analyses[0].entities)
    ).entities


def calls(entities):
    return [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]


def test_case_insensitive_symbols_calls_class_accessors_and_shadowing():
    text = """Option Explicit
Class Repo
 Private field
 Public Function Read(ByVal id)
   Dim field
   field = id
   Read = field
 End Function
 Property Get Title()
   Title = field
 End Property
 Property Let Title(value)
   field = value
 End Property
 Property Set Title(value)
   Set field = value
 End Property
End Class
Sub Log(id)
End Sub
Dim repoObject
Set repoObject = New Repo
Call repoObject.rEAd(1)
Call LOG(2)
lOg 3
"""
    entities = facts(text)
    symbols = [e for e in entities if isinstance(e, Symbol)]
    names = {e.qualified_name: e for e in symbols}
    assert {
        "repo.read",
        "repo.title.get",
        "repo.title.let",
        "repo.title.set",
    } <= names.keys()
    assert names["repo.read"].signature.parameter_types[0].name == "vbscript.Variant"
    assert len([s for s in symbols if s.name == "field"]) == 2
    log = next(s for s in symbols if s.name == "log")
    matched = [
        c
        for c in calls(entities)
        if c.resolution.target and c.resolution.target.id == log.id
    ]
    assert len(matched) == 2
    assert {c.certainty for c in matched} == {"INFERRED"}
    assert any(
        c.resolution.target and c.resolution.target.id == names["repo.read"].id
        for c in calls(entities)
    )
    assert list(facts(text)) == list(facts(text))
    assert {s.id for s in symbols} == {
        e.id for e in facts(text.replace("Sub Log", "Sub LOG")) if isinstance(e, Symbol)
    }


def test_unused_sql_function_does_not_assert_execution():
    entities = facts("""Function Build(id)
Dim q
q="DELETE FROM users WHERE id=" & id
Build=q
End Function
""")
    assert any(isinstance(e, SqlConstruction) for e in entities)
    assert not any(isinstance(e, SqlExecute) for e in entities)
    assert not any(
        isinstance(e, Relation)
        and e.relation_kind
        in (RelationKind.EXECUTES_SQL, RelationKind.EXECUTES_STATEMENT)
        for e in entities
    )
    assert not any(isinstance(e, DataAccess) for e in entities)


def test_connection_alias_execution_and_utf8_evidence():
    text = '\ufeff\'Привет\r\nSet CN=CreateObject("adodb.connection")\r\nCN.Open "fake"\r\nSet alias=cn\r\nq="DELETE " & _\r\n "FROM ""пользователи"""\r\nalias.ExEcUtE q\r\n'
    entities = facts(text)
    sink = next(e for e in entities if isinstance(e, SqlExecute))
    assert sink.api == "ADODB.Connection.Execute" and sink.sql_argument_index == 0
    relations = [
        e
        for e in entities
        if isinstance(e, Relation)
        and e.relation_kind == RelationKind.EXECUTES_STATEMENT
    ]
    assert len(relations) == 1 and relations[0].resolution.status == "RESOLVED"
    statement = next(
        e
        for e in entities
        if isinstance(e, SqlStatement) and e.id == relations[0].resolution.target.id
    )
    assert statement.text == 'DELETE FROM "пользователи"'
    location = relations[0].evidence[0].source_range
    lines = text.encode().split(b"\n")
    start = (
        sum(len(line) + 1 for line in lines[: location.start.line - 1])
        + location.start.byte_column
    )
    end = (
        sum(len(line) + 1 for line in lines[: location.end.line - 1])
        + location.end.byte_column
    )
    assert text.encode()[start:end] == b"alias.ExEcUtE q"
    assert any(
        isinstance(e, DataAccess) and e.access_kind == "DELETE" for e in entities
    )
    assert all(
        e.certainty != "STATIC_PROVEN"
        for e in entities
        if isinstance(e, (Relation, ExternalReference))
    )
    assert (
        next(e for e in entities if isinstance(e, SourceAnalysis)).adapter_key
        == "vbscript"
    )


@pytest.mark.parametrize(
    "kind, setup, call",
    [
        (
            "ADODB.Command",
            'cmd.CommandText="UPDATE users SET name=1"\ncmd.CommandType=1',
            "cmd.Execute",
        ),
        ("ADODB.Recordset", "", 'cmd.Open "SELECT id FROM users"'),
        (
            "ADODB.Connection",
            "",
            'cmd.Execute("DELETE FROM users; INSERT INTO users(id) VALUES(1)")',
        ),
    ],
)
def test_known_adodb_shapes_and_multiple_statements(kind, setup, call):
    entities = facts(f'Set cmd=CreateObject("{kind}")\n{setup}\n{call}\n')
    assert any(isinstance(e, SqlExecute) for e in entities)
    links = [
        e
        for e in entities
        if isinstance(e, Relation)
        and e.relation_kind == RelationKind.EXECUTES_STATEMENT
    ]
    assert len(links) == (2 if ";" in call else 1)
    assert all(link.evidence and link.coverage.status == "PARTIAL" for link in links)


@pytest.mark.parametrize(
    "prefix",
    [
        "Set conn=OtherFactory()",
        "Set conn=CreateObject(progID)",
        'Set conn=CreateObject("Custom.Connection")',
        'Set conn=CreateObject("ADODB.Connection")\nSet conn=OtherFactory()',
        'Set conn=CreateObject("ADODB.Connection")\nCall Unknown(conn)',
        'If enabled Then\nSet conn=CreateObject("ADODB.Connection")\nEnd If',
        'Function CreateObject(x)\nEnd Function\nSet conn=CreateObject("ADODB.Connection")',
        'Set conn=CreateObject("ADODB.Connection")\nEval "x"',
    ],
)
def test_unproven_or_invalidated_receiver_never_becomes_sql_sink(prefix):
    entities = facts(prefix + '\nconn.Execute "DELETE FROM users"\n')
    assert any(isinstance(e, SqlConstruction) for e in entities)
    assert not any(isinstance(e, SqlExecute) for e in entities)
    assert any(
        isinstance(e, ExternalReference) and e.selector.qualified_name == "conn.execute"
        for e in entities
    )


def test_command_type_stored_procedure_does_not_bind_sql_text():
    entities = facts(
        'Set c=CreateObject("ADODB.Command")\nc.CommandText="DELETE FROM users"\nc.CommandType=4\nc.Execute\n'
    )
    assert any(isinstance(e, SqlExecute) for e in entities)
    assert not any(
        isinstance(e, Relation) and e.relation_kind == RelationKind.EXECUTES_STATEMENT
        for e in entities
    )


def test_partial_dynamic_sql_has_evidence_but_no_proven_semantics():
    entities = facts(
        'Sub Run(id)\nDim conn,q\nSet conn=CreateObject("ADODB.Connection")\nq="DELETE FROM users WHERE id=" & id\nconn.Execute q\nEnd Sub\n'
    )
    links = [
        e
        for e in entities
        if isinstance(e, Relation)
        and e.relation_kind == RelationKind.EXECUTES_STATEMENT
    ]
    assert links and all(e.resolution.status == "PARTIAL" for e in links)
    assert not any(isinstance(e, DataAccess) for e in entities)
    assert any(
        d.code == "vbscript.SQL_PARTIAL"
        for e in entities
        if isinstance(e, SourceAnalysis)
        for d in e.diagnostics
    )


def test_dynamic_dispatch_and_remote_targets_stay_external():
    entities = facts(
        'Sub Local()\nEnd Sub\nExecuteGlobal "generated"\nCall LOCAL()\nCall Remote.Invoke(1)\nSet x=New MissingClass\n'
    )
    local = next(e for e in entities if isinstance(e, Symbol) and e.name == "local")
    assert any(
        e.resolution.status == "PARTIAL"
        and any(c.id == local.id for c in e.resolution.candidates)
        for e in calls(entities)
    )
    selectors = {
        e.selector.qualified_name for e in entities if isinstance(e, ExternalReference)
    }
    assert {"executeglobal", "remote.invoke", "missingclass"} <= selectors


def test_with_redim_comments_and_empty_script():
    facts(
        'Rem\nDim a()\nReDim Preserve a(2)\nWith obj\n .Execute "DELETE FROM users"\nEnd With\n'
    )
    assert len([e for e in facts("") if isinstance(e, Symbol)]) == 2


@pytest.mark.parametrize(
    "text",
    [
        "Sub Broken(\n",
        "Sub X()\nEnd Function\n",
        "Sub Name()\nEnd Sub\nSub NAME()\nEnd Sub\n",
        "Option Explicit\nx=1\n",
    ],
)
def test_errors_are_structured_and_do_not_return_partial_facts(text, capsys):
    with pytest.raises(AdapterError) as failure:
        facts(text)
    assert failure.value.adapter_key == "vbscript"
    assert failure.value.issues[0].path == "A.vbs"
    assert failure.value.issues[0].diagnostic.severity == "ERROR"
    assert not capsys.readouterr().err


def test_parser_and_recovery_budgets_are_bounded(monkeypatch):
    src = source("A.vbs", "", "vbscript")
    raw = b"\xffinvalid"
    invalid = SourceInput(
        src.file.model_copy(update={"content_sha256": hashlib.sha256(raw).hexdigest()}),
        raw,
    )
    assert parse_vbscript(invalid).diagnostics[0].code == "vbscript.INVALID_UTF8"
    assert (
        parse_vbscript(source("A.vbs", "x=" + "(" * 65 + "1" + ")" * 65, "vbscript"))
        .diagnostics[0]
        .code
        == "vbscript.RESOURCE_LIMIT"
    )
    monkeypatch.setattr("code_crawler.vbscript_parse.MAX_TOKENS", 5)
    assert (
        parse_vbscript(source("A.vbs", "Dim a,b,c,d,e,f", "vbscript"))
        .diagnostics[0]
        .code
        == "vbscript.RESOURCE_LIMIT"
    )
    monkeypatch.undo()
    with pytest.raises(AdapterError, match="budget"):
        facts('q="DELETE FROM users"\n' + "q=q & q\n" * 20)


def test_suffix_routes_and_dialect_identity():
    registry = AdapterRegistry((VbscriptSourceAdapter(),))
    assert registry.route("script.VbS").key == "vbscript"
    assert registry.route("script.vbe") is None
    with pytest.raises(ValueError):
        VbscriptSourceAdapter(dialect="bogus")


@pytest.mark.parametrize(
    "call", ["conn.Execute q, Unknown(q)", "x=conn.Execute(q,Unknown(q))"]
)
def test_argument_side_effect_invalidates_receiver_before_sink_classification(call):
    entities = facts(
        'Set conn=CreateObject("ADODB.Connection")\nq="DELETE FROM users"\n'
        + call
        + "\n"
    )
    assert not any(isinstance(e, SqlExecute) for e in entities)


def test_differently_scoped_files_are_not_implicitly_included():
    sources = (
        source("A.vbs", "Sub Work()\nEnd Sub\n", "vbscript"),
        source("B.vbs", "Call WORK()\n", "vbscript"),
    )
    _, analyses = run(AdapterRegistry((VbscriptSourceAdapter(),)), sources)
    batch = UcmBatch(
        repository_id=REPO,
        entities=tuple(s.file for s in sources)
        + tuple(e for a in analyses for e in a.entities),
    )
    assert not any(c.resolution.status == "RESOLVED" for c in calls(batch.entities))
    assert any(
        isinstance(e, ExternalReference) and e.selector.qualified_name == "work"
        for e in batch.entities
    )


def test_adodb_records_affected_rebinding_invalidates_following_receiver():
    entities = facts(
        'Set c=CreateObject("ADODB.Connection")\nc.Execute "DELETE FROM users", c\nc.Execute "DELETE FROM accounts"\n'
    )
    assert len([e for e in entities if isinstance(e, SqlExecute)]) == 1


def test_const_writes_fail_and_dialect_is_explicit():
    with pytest.raises(AdapterError, match="assignment to a VBScript Const"):
        facts('Const q="DELETE FROM users"\nq="DELETE FROM accounts"\n')
    entities = facts('q="SELECT id FROM [users]"\n', dialect="tsql")
    assert all(e.dialect == "tsql" for e in entities if isinstance(e, SqlStatement))
    assert any(
        isinstance(e, DataAccess) and e.table_name.normalized == "users"
        for e in entities
    )


def test_known_string_plus_is_distinct_from_unknown_variant_arithmetic():
    known = facts(
        'Set c=CreateObject("ADODB.Connection")\nc.Execute "DELETE " + "FROM users"\n'
    )
    assert any(
        isinstance(e, Relation)
        and e.relation_kind == RelationKind.EXECUTES_STATEMENT
        and e.resolution.status == "RESOLVED"
        for e in known
    )
    unknown = facts(
        'Sub Run(id)\nDim c,q\nSet c=CreateObject("ADODB.Connection")\nq="DELETE FROM users WHERE id=" + id\nc.Execute q\nEnd Sub\n'
    )
    assert any(isinstance(e, SqlConstruction) for e in unknown)
    assert not any(
        isinstance(e, Relation) and e.relation_kind == RelationKind.EXECUTES_STATEMENT
        for e in unknown
    )


def test_embedded_nul_is_rejected_before_fact_storage():
    result = parse_vbscript(source("A.vbs", 'q="DELETE FROM users\x00"', "vbscript"))
    assert (
        result.tree is None
        and result.diagnostics[0].code == "vbscript.INVALID_CHARACTER"
    )
    with pytest.raises(AdapterError) as failure:
        facts('q="DELETE FROM users\x00"')
    assert failure.value.issues[0].diagnostic.code == "vbscript.INVALID_CHARACTER"
