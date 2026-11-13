import asyncio
import hashlib
from uuid import UUID

import pytest

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_symbols import analyze_files, extract
from code_crawler.ucm import (
    EntityDocument,
    EntityType,
    Occurrence,
    Relation,
    RelationKind,
    SourceFile,
    Symbol,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")


def source(text: str, path: str = "A.java") -> SourceInput:
    content = text.encode()
    file = SourceFile(
        repository_id=str(REPO),
        logical_key=path,
        name=path,
        path=path,
        language="java",
        id=logical_id(str(REPO), EntityType.SOURCE_FILE, path),
        content_sha256=hashlib.sha256(content).hexdigest(),
    )
    return SourceInput(file, content)


def collect(text: str):
    captured = source(text)
    result = extract(captured)
    batch = UcmBatch(
        repository_id=REPO, entities=(captured.file, *result.analysis.entities)
    )
    assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
    return result


def test_overloads_constructors_parameters_and_arrays() -> None:
    result = collect("""package p; class A {
        A(int x) {} void A(int x) {}
        void m(int x) {} void m(String x) {}
        void arrays(int x[], String... rest) {}
    }""")
    symbols = [e for e in result.analysis.entities if isinstance(e, Symbol)]
    methods = [s for s in symbols if s.symbol_kind in ("METHOD", "CONSTRUCTOR")]
    assert len({s.id for s in methods}) == 5
    assert {s.name for s in methods} == {"<init>", "A", "m", "arrays"}
    arrays = next(s for s in methods if s.name == "arrays")
    assert [t.name for t in arrays.signature.parameter_types] == ["int[]", "String[]"]
    assert len([s for s in symbols if s.symbol_kind == "PARAMETER"]) == 6


def test_identity_is_stable_across_comments_and_body_edits() -> None:
    a = collect("class A { int m(int x) { return x; } }")
    b = collect(
        "// new comment\nclass A { int m(int renamed) { int y=1; return renamed+y; } }"
    )
    method = lambda result: next(
        e for e in result.analysis.entities if isinstance(e, Symbol) and e.name == "m"
    )
    assert method(a).id == method(b).id
    assert method(a).source_range != method(b).source_range


def test_generic_parameters_preserve_type_ref_but_use_syntactic_erasure() -> None:
    result = collect(
        "class A { void m(java.util.List<String> items, int[][] numbers) {} }"
    )
    method = next(
        e for e in result.analysis.entities if isinstance(e, Symbol) and e.name == "m"
    )
    parameter = next(
        e
        for e in result.analysis.entities
        if isinstance(e, Symbol) and e.name == "items"
    )
    assert [r.name for r in method.signature.parameter_types] == [
        "java.util.List",
        "int[][]",
    ]
    assert parameter.type_ref.name == "java.util.List<String>"


def test_parameter_field_shadowing_this_field_and_foreign_receiver() -> None:
    result = collect(
        "class A { int x; void m(int x, A other) { x=1; this.x=x; other.x=x; } }"
    )
    symbols = {e.id: e for e in result.analysis.entities if isinstance(e, Symbol)}
    occurrences = [
        e
        for e in result.analysis.entities
        if isinstance(e, Occurrence)
        and e.name == "x"
        and e.occurrence_kind != "DECLARATION"
    ]
    writes = [e for e in occurrences if e.occurrence_kind == "WRITE"]
    assert [
        symbols[e.target_symbol_id].symbol_kind if e.target_symbol_id else None
        for e in writes
    ] == ["PARAMETER", "FIELD", None]
    assert all(
        symbols[e.target_symbol_id].symbol_kind == "PARAMETER"
        for e in occurrences
        if e.occurrence_kind == "READ"
    )


def test_nested_locals_and_compound_accesses_do_not_leak() -> None:
    result = collect("class A { int x; void m() { x++; { int x=0; x+=1; } x=2; } }")
    symbols = {e.id: e for e in result.analysis.entities if isinstance(e, Symbol)}
    uses = [
        e
        for e in result.analysis.entities
        if isinstance(e, Occurrence)
        and e.name == "x"
        and e.occurrence_kind != "DECLARATION"
    ]
    assert [
        (e.occurrence_kind, symbols[e.target_symbol_id].symbol_kind) for e in uses
    ] == [
        ("READ", "FIELD"),
        ("WRITE", "FIELD"),
        ("READ", "LOCAL_VARIABLE"),
        ("WRITE", "LOCAL_VARIABLE"),
        ("WRITE", "FIELD"),
    ]


def test_overloaded_calls_are_candidates_not_confirmed_edges() -> None:
    result = collect(
        "class A { void m(int x) {} void m(String x) {} void run(){ m(1); missing(); } }"
    )
    calls = [
        e
        for e in result.analysis.entities
        if isinstance(e, Occurrence) and e.occurrence_kind == "CALL"
    ]
    assert [(c.name, c.resolution, c.target_symbol_id) for c in calls] == [
        ("m", "AMBIGUOUS", None),
        ("missing", "UNRESOLVED", None),
    ]
    relation = next(
        e
        for e in result.analysis.entities
        if isinstance(e, Relation) and e.source.id == calls[0].id
    )
    assert len(relation.resolution.candidates) == 2
    assert all(
        e.relation_kind != RelationKind.CALLS
        for e in result.analysis.entities
        if isinstance(e, Relation)
    )


def test_unicode_occurrence_ranges_and_declaration_evidence() -> None:
    text = "class Пример { int поле; int m(){ return поле; } }"
    result = collect(text)
    use = next(
        e
        for e in result.analysis.entities
        if isinstance(e, Occurrence)
        and e.name == "поле"
        and e.occurrence_kind == "READ"
    )
    start, end = use.source_range.start.byte_column, use.source_range.end.byte_column
    assert text.encode()[start:end] == "поле".encode()
    assert use.resolution == "RESOLVED"
    declarations = [
        e
        for e in result.analysis.entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.DECLARES
    ]
    assert declarations and all(
        e.evidence and e.coverage.status == "PARTIAL" for e in declarations
    )
    for entity in result.analysis.entities:
        assert (
            EntityDocument.model_validate_json(entity.model_dump_json()).root == entity
        )


def test_excluded_scopes_do_not_produce_false_local_bindings() -> None:
    result = collect(
        "class A { int x; void m(){ Runnable r=()->{ int x=1; x++; }; x=2; } }"
    )
    locals = [
        e.name
        for e in result.analysis.entities
        if isinstance(e, Symbol) and e.symbol_kind == "LOCAL_VARIABLE"
    ]
    assert locals == ["r"]
    assert result.coverage.status == "PARTIAL"


def test_invalid_source_returns_diagnostics_and_hash_mismatch_is_rejected() -> None:
    captured = source("class A { int x }")
    result = extract(captured)
    assert result.diagnostics and result.coverage.status == "PARTIAL"
    with pytest.raises(ValueError, match="fingerprint"):
        extract(SourceInput(captured.file, b"class B {}"))


def test_duplicate_callable_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        collect("class A { void m(String[] x) {} void m(String... x) {} }")


def test_incremental_callback_uses_existing_contract() -> None:
    captured = source("class A {}")
    analyses = asyncio.run(analyze_files((captured,)))
    assert analyses == (extract(captured).analysis,)


def test_pattern_binding_body_is_excluded_instead_of_binding_to_field() -> None:
    result = collect(
        "class A { int x; void m(Object o) { if(o instanceof String x){ x.length(); } } }"
    )
    assert any(
        isinstance(e, Symbol) and e.name == "m" for e in result.analysis.entities
    )
    assert not any(
        isinstance(e, Occurrence)
        and e.name == "x"
        and e.occurrence_kind != "DECLARATION"
        for e in result.analysis.entities
    )


def test_canonical_callback_rejects_parser_errors_instead_of_losing_diagnostics() -> (
    None
):
    with pytest.raises(ValueError, match="parser diagnostics"):
        asyncio.run(analyze_files((source("class A { int x }"),)))


def test_same_field_names_are_scoped_to_their_declaring_class() -> None:
    result = collect(
        "class A { int x; int m(){ return x; } } class B { int x; int m(){ return x; } }"
    )
    symbols = {e.id: e for e in result.analysis.entities if isinstance(e, Symbol)}
    reads = [
        e
        for e in result.analysis.entities
        if isinstance(e, Occurrence) and e.name == "x" and e.occurrence_kind == "READ"
    ]
    assert [symbols[e.target_symbol_id].qualified_name for e in reads] == ["A.x", "B.x"]


def test_local_visibility_starts_at_declaration() -> None:
    result = collect("class A { int x; void m(){ x=1; int x=0; x=2; } }")
    symbols = {e.id: e for e in result.analysis.entities if isinstance(e, Symbol)}
    writes = [
        e
        for e in result.analysis.entities
        if isinstance(e, Occurrence) and e.name == "x" and e.occurrence_kind == "WRITE"
    ]
    assert [symbols[e.target_symbol_id].symbol_kind for e in writes] == [
        "FIELD",
        "LOCAL_VARIABLE",
    ]
