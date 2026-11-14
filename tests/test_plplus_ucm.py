import asyncio
import hashlib
from uuid import UUID

import pytest

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.plplus_adapter import PlplusSourceAdapter
from code_crawler.plplus_parse import parse_plplus
from code_crawler.plplus_ucm import build_plplus
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.ucm import (
    EntityType,
    ExternalReference,
    Occurrence,
    Relation,
    RelationKind,
    SourceAnalysis,
    SourceFile,
    SqlStatement,
    Symbol,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")
PATH = "exports/CLIENT/methods/EDIT/src/execute.plp"


def source(text, path=PATH):
    content = text.encode() if isinstance(text, str) else text
    return SourceInput(
        SourceFile(
            repository_id=str(REPO),
            logical_key=path,
            id=logical_id(str(REPO), EntityType.SOURCE_FILE, path),
            name=path,
            path=path,
            language="plplus",
            content_sha256=hashlib.sha256(content).hexdigest(),
        ),
        content,
    )


def result(text, path=PATH):
    _, results = build_plplus((source(text, path),))
    r = results[path]
    assert not any(d.severity == "ERROR" for d in r.diagnostics), r.diagnostics
    return r


def facts(text, cls, path=PATH):
    return [e for e in result(text, path).analysis.entities if isinstance(e, cls)]


def accesses(text, path=PATH):
    return [
        (e.selector.qualified_name, e.evidence[0].rule)
        for e in facts(text, ExternalReference, path)
        if e.evidence[0].rule.startswith("cft.")
    ]


def test_symbols_signatures_and_source_owners():
    symbols = facts(
        "function F(p in number) return varchar2 is r varchar2(30); begin return r; end;",
        Symbol,
    )
    assert next(s for s in symbols if s.name == "cft::CLIENT").symbol_kind == "CLASS"
    assert next(s for s in symbols if s.name == "EDIT").symbol_kind == "METHOD"
    f = next(s for s in symbols if s.name == "F")
    assert f.signature.parameter_types[0].name == "NUMBER"
    assert f.signature.return_type.name == "VARCHAR2"
    assert next(s for s in symbols if s.name == "P").symbol_kind == "PARAMETER"
    assert next(s for s in symbols if s.name == "R").type_ref.name == "VARCHAR2(30)"


def test_unknown_path_does_not_guess_cft_class():
    symbols = facts("begin [A] := 1; end;", Symbol, "misc/execute.plp")
    assert symbols[0].qualified_name == "<unit:misc/execute.plp>"
    assert ("cft.attribute::<unknown>::A", "cft.WRITE.ATTRIBUTE.write") in accesses(
        "begin [A] := 1; end;", "misc/execute.plp"
    )


def test_criteria_owner():
    symbols = facts(
        "type main is select x(x.[A]) in ::[C];",
        Symbol,
        "C/criteria/VIEW/src/condition.plp",
    )
    assert any(s.name == "VIEW" for s in symbols)


def test_unicode_byte_columns_and_case_insensitive_names():
    text = "имя number; begin имя := 1; end;"
    symbols = facts(text, Symbol)
    variable = next(s for s in symbols if s.name == "ИМЯ")
    assert variable.source_range.end.byte_column == 6
    ref = next(o for o in facts(text, Occurrence) if o.occurrence_kind == "WRITE")
    assert ref.target_symbol_id == variable.id
    assert ref.source_range.start.byte_column == 21


@pytest.mark.parametrize(
    "text",
    [b"\xff", b"function f(", b"begin @; end;", b"begin x := 'unterminated; end;"],
)
def test_parse_errors_suppress_facts(text, capsys):
    src = source(text)
    _, results = build_plplus((src,))
    r = results[PATH]
    assert r.diagnostics
    assert not r.analysis.entities
    assert all(c.status == "UNSUPPORTED" for c in r.capabilities[1:])
    assert not capsys.readouterr().err


def test_nested_lexical_shadowing():
    text = "x number; procedure f(x in number) is begin x := 1; declare x number; begin x := 2; end; x := 3; end;"
    symbols = facts(text, Symbol)
    parameter = next(
        s for s in symbols if s.name == "X" and s.symbol_kind == "PARAMETER"
    )
    refs = [r for r in facts(text, Occurrence) if r.occurrence_kind == "WRITE"]
    assert refs[0].target_symbol_id == refs[2].target_symbol_id == parameter.id
    assert refs[1].target_symbol_id != parameter.id


def test_loop_variable_scope_does_not_escape():
    text = "i number; begin for i in 1..10 loop i := 2; end loop; i := 3; end;"
    refs = [r for r in facts(text, Occurrence) if r.occurrence_kind == "WRITE"]
    assert refs[0].target_symbol_id != refs[1].target_symbol_id


def test_quoted_identifier_case_is_preserved():
    text = '"a" number; "A" number; begin "a" := "A"; end;'
    refs = [
        r for r in facts(text, Occurrence) if r.occurrence_kind in ("READ", "WRITE")
    ]
    assert all(r.resolution == "RESOLVED" for r in refs)
    assert refs[0].target_symbol_id != refs[1].target_symbol_id


def test_forward_spec_and_body_share_symbol_without_duplicate_identity():
    text = "procedure f(p number); procedure f(p number) is begin null; end; begin f(1); end;"
    symbols = facts(text, Symbol)
    assert len([s for s in symbols if s.name == "F"]) == 1
    calls = [r for r in facts(text, Relation) if r.relation_kind == RelationKind.CALLS]
    assert len(calls) == 1 and calls[0].resolution.status == "PARTIAL"


def test_nested_short_calls_and_missing_targets():
    text = "procedure f is procedure g is begin null; end; begin g(); missing(); end;"
    calls = [r for r in facts(text, Relation) if r.relation_kind == RelationKind.CALLS]
    assert len(calls) == 1
    assert any(
        e.selector.qualified_name.startswith("plplus.call::missing")
        for e in facts(text, ExternalReference)
    )


def test_no_parentheses_procedure_call():
    assert any(
        r.relation_kind == RelationKind.CALLS
        for r in facts("procedure f is begin null; end; begin f; end;", Relation)
    )


def test_queries_are_cft_not_sql():
    text = "r number; begin select x(x.[A]) in ::[C] where x.[B]=1 into r; end;"
    a = accesses(text)
    assert ("cft.class::C", "cft.READ.CLASS") in a
    assert ("cft.attribute::C::A", "cft.READ.ATTRIBUTE.select") in a
    assert ("cft.attribute::C::B", "cft.READ.ATTRIBUTE.where") in a
    assert not facts(text, SqlStatement)


@pytest.mark.parametrize(
    "text,cls,mode",
    [
        ("update x(x.[A]=x.[B]) in ::[C] where x.[Z]=1;", "C", "UPDATE"),
        ("delete x in ::[C] where x.[Z]=1;", "C", "DELETE"),
        ("insert into ::[C] x(x.[A]=1);", "C", "INSERT"),
        ("locate x in ::[C] where x.[Z]=1;", "C", "READ"),
    ],
)
def test_dml_class_modes(text, cls, mode):
    a = accesses("begin " + text + " end;")
    assert ("cft.class::" + cls, "cft." + mode + ".CLASS") in a
    assert all(
        rule == "cft.READ.ATTRIBUTE.where"
        for selector, rule in a
        if selector.endswith("::Z")
    )


def test_update_rhs_remains_read():
    a = accesses("begin update x(x.[A]=x.[B]) in ::[C] where x.[Z]=1; end;")
    assert ("cft.attribute::C::A", "cft.WRITE.ATTRIBUTE.write") in a
    assert ("cft.attribute::C::B", "cft.READ.ATTRIBUTE.select") in a


def test_own_attribute_write():
    assert ("cft.attribute::CLIENT::A", "cft.WRITE.ATTRIBUTE.write") in accesses(
        "begin [A] := [B]; end;"
    )
    assert ("cft.attribute::CLIENT::B", "cft.READ.ATTRIBUTE.select") in accesses(
        "begin [A] := [B]; end;"
    )


def test_nested_queries_do_not_mix_aliases():
    text = "r number; begin select x(x.[A]) in ::[OUTER_C] where exists(select x(x.[B]) in ::[INNER_C] where x.[D]=1) into r; end;"
    a = accesses(text)
    assert ("cft.attribute::OUTER_C::A", "cft.READ.ATTRIBUTE.select") in a
    assert ("cft.attribute::INNER_C::B", "cft.READ.ATTRIBUTE.select") in a
    assert ("cft.attribute::INNER_C::D", "cft.READ.ATTRIBUTE.where") in a


def test_ambiguous_alias_not_bound_to_arbitrary_class():
    text = "r number; begin select x(x.[A]) in ::[C], ::[D] into r; end;"
    assert ("cft.attribute::<unknown>::A", "cft.READ.ATTRIBUTE.select") in accesses(
        text
    )


def test_class_reference_in_dml_predicate_is_read():
    a = accesses("begin delete x in ::[C] where x.[A]=::[OTHER]; end;")
    assert ("cft.class::OTHER", "cft.READ.CLASS") in a


def test_macros_and_preprocessor_are_diagnosed():
    r = result("--#ifdef X\nbegin &debug(1); null; end;\n--#else\nbad syntax\n--#endif")
    assert r.diagnostics
    assert all(d.severity == "WARNING" for d in r.diagnostics)
    assert all(c.status != "COMPLETE" for c in r.capabilities[1:])


def test_execute_immediate_does_not_invent_execution_or_cft_access():
    assert not accesses("begin execute immediate 'delete from users'; end;")


def test_cross_section_catalog_and_changed_definitions_invalidate_version():
    definition = source(
        "procedure f(p number) is begin null; end;",
        "exports/CLIENT/methods/EDIT/src/private.plp",
    )
    caller = source("begin f(1); end;")
    version, results = build_plplus((definition, caller))
    calls = [
        r
        for r in results[PATH].analysis.entities
        if isinstance(r, Relation) and r.relation_kind == RelationKind.CALLS
    ]
    assert calls and calls[0].resolution.status == "PARTIAL"
    assert definition.file.path in results[PATH].analysis.dependencies
    changed = source("procedure g(p number) is begin null; end;", definition.file.path)
    next_version, next_results = build_plplus((changed, caller))
    assert version != next_version
    assert not any(
        isinstance(r, Relation) and r.relation_kind == RelationKind.CALLS
        for r in next_results[PATH].analysis.entities
    )


def test_explicit_cft_call_is_not_attribute_read():
    refs = facts("begin ::[C].[M].f(1); end;", ExternalReference)
    assert len(refs) == 1
    assert refs[0].selector.qualified_name == "cft.call::C::M::F"


def test_registry_and_batch_validate():
    async def run():
        inputs = (
            source(
                "procedure f is begin null; end;",
                "exports/CLIENT/methods/EDIT/src/private.plp",
            ),
            source("begin f; [A] := 1; end;"),
        )
        registry = AdapterRegistry((PlplusSourceAdapter(),))
        assert registry.route(PATH).key == "plplus"
        prepared = await registry.prepare(inputs)
        results = await prepared(inputs)
        reports = [
            e for r in results for e in r.entities if isinstance(e, SourceAnalysis)
        ]
        assert len(reports) == 2
        UcmBatch(
            repository_id=REPO,
            entities=tuple(s.file for s in inputs)
            + tuple(e for r in results for e in r.entities),
        )

    asyncio.run(run())


def test_duplicate_subprogram_bodies_fail_closed():
    src = source("procedure f is begin null; end; procedure f is begin null; end;")
    _, results = build_plplus((src,))
    assert results[PATH].diagnostics
    assert not results[PATH].analysis.entities


def test_parser_prediction_mode():
    parsed = parse_plplus(source("begin null; end;"))
    assert parsed.prediction_mode in ("SLL", "LL")
    assert not parsed.diagnostics


def test_select_into_and_fetch_are_variable_writes():
    text = "r number; c number; begin select x(x.[A]) in ::[C] into r; fetch c into r; end;"
    refs = [
        r
        for r in facts(text, Occurrence)
        if r.name == "r" and r.occurrence_kind != "DECLARATION"
    ]
    assert len(refs) == 2
    assert all(
        r.occurrence_kind == "WRITE" and r.resolution == "RESOLVED" for r in refs
    )


def test_class_constructor_query_source_is_not_operation_call():
    a = accesses("r number; begin select x(x.[A]) in ::[C]([CODE]='x') into r; end;")
    assert ("cft.class::C", "cft.READ.CLASS") in a
    assert ("cft.attribute::C::A", "cft.READ.ATTRIBUTE.select") in a


def test_overloads_remain_ambiguous():
    calls = [
        r
        for r in facts(
            "procedure f(p number); procedure f(p varchar2); begin f(1); end;", Relation
        )
        if r.relation_kind == RelationKind.CALLS
    ]
    assert calls[0].resolution.status == "AMBIGUOUS"
    assert len(calls[0].resolution.candidates) == 2


def test_sources_from_different_export_roots_are_not_merged():
    inputs = (
        source(
            "procedure f is begin null; end;",
            "other/CLIENT/methods/EDIT/src/private.plp",
        ),
        source("begin f; end;"),
    )
    _, results = build_plplus(inputs)
    assert not any(
        isinstance(r, Relation) and r.relation_kind == RelationKind.CALLS
        for r in results[PATH].analysis.entities
    )


def test_identical_section_names_in_different_operations_have_distinct_ids():
    inputs = (
        source("procedure f is begin null; end;"),
        source(
            "procedure f is begin null; end;",
            "exports/CLIENT/methods/OTHER/src/execute.plp",
        ),
    )
    _, results = build_plplus(inputs)
    ids = [e.id for r in results.values() for e in r.analysis.entities]
    assert len(ids) == len(set(ids))


def test_constructor_attribute_belongs_to_constructor_class():
    a = accesses("r number; begin select x(x.[A]) in ::[C]([CODE]='x') into r; end;")
    assert ("cft.attribute::C::CODE", "cft.READ.ATTRIBUTE.select") in a


def test_collection_alias_blocks_outer_query_alias():
    text = "r number; begin select x(x.[A]) in ::[OUTER_C] where exists(select x(x.[B]) in (select y(y.[Z]) in ::[INNER_C])) into r; end;"
    assert ("cft.attribute::<unknown>::B", "cft.READ.ATTRIBUTE.select") in accesses(
        text
    )


def test_qualified_call_does_not_resolve_to_same_named_root_function():
    text = "procedure obj is begin null; end; begin obj.f(); end;"
    assert not any(r.relation_kind == RelationKind.CALLS for r in facts(text, Relation))


def test_assignment_alias_targets_are_writes():
    text = "a number; b number; begin a = b := 1; end;"
    refs = [r for r in facts(text, Occurrence) if r.occurrence_kind != "DECLARATION"]
    assert len(refs) == 2 and all(r.occurrence_kind == "WRITE" for r in refs)
