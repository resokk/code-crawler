import asyncio
import hashlib
from uuid import UUID

import pytest

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_calls import JavaCallAnalyzer
from code_crawler.ucm import (
    EntityType,
    ExternalReference,
    Occurrence,
    Relation,
    RelationKind,
    SourceFile,
    Symbol,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")


def source(path: str, text: str) -> SourceInput:
    content = text.encode()
    return SourceInput(
        SourceFile(
            repository_id=str(REPO),
            logical_key=path,
            path=path,
            name=path,
            language="java",
            id=logical_id(str(REPO), EntityType.SOURCE_FILE, path),
            content_sha256=hashlib.sha256(content).hexdigest(),
        ),
        content,
    )


def analyze(files: dict[str, str]) -> UcmBatch:
    inputs = tuple(source(path, text) for path, text in files.items())
    analyzer = JavaCallAnalyzer(inputs)
    analyses = asyncio.run(analyzer(inputs))
    batch = UcmBatch(
        repository_id=REPO,
        entities=tuple(s.file for s in inputs)
        + tuple(e for a in analyses for e in a.entities),
    )
    assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
    return batch


def calls(batch: UcmBatch) -> list[Relation]:
    return [
        e
        for e in batch.entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]


def test_overloads_primitive_widening_and_recursion() -> None:
    batch = analyze(
        {
            "A.java": """class A {
        void m(int x) {} void m(String x) {} void wide(long x) {} void wide(double x) {}
        void run(){ m(1); m("x"); wide(1); run(); }
    }"""
        }
    )
    symbols = {e.id: e for e in batch.entities if isinstance(e, Symbol)}
    edges = calls(batch)
    assert all(e.resolution.status == "RESOLVED" for e in edges)
    signatures = [
        tuple(t.name for t in symbols[e.resolution.target.id].signature.parameter_types)
        for e in edges
    ]
    assert signatures == [("int",), ("String",), ("long",), ()]
    assert edges[-1].source.id == edges[-1].resolution.target.id
    assert all(
        e.certainty.value == "INFERRED"
        and e.coverage.status == "PARTIAL"
        and e.evidence
        for e in edges
    )


def test_cross_file_controller_service_repository_chain() -> None:
    batch = analyze(
        {
            "Controller.java": "package p; class Controller { Service service; void handle(){ service.run(); } }",
            "Service.java": "package p; class Service { Repository repo; void run(){ repo.save(1); } }",
            "Repository.java": "package p; class Repository { void save(int id) {} }",
        }
    )
    symbols = {e.id: e for e in batch.entities if isinstance(e, Symbol)}
    assert {
        (
            symbols[e.source.id].qualified_name,
            symbols[e.resolution.target.id].qualified_name,
        )
        for e in calls(batch)
    } == {
        ("p.Controller.handle", "p.Service.run"),
        ("p.Service.run", "p.Repository.save"),
    }


def test_imports_static_receiver_and_chained_return_type() -> None:
    batch = analyze(
        {
            "Client.java": "package a; import b.Service; class Client { Service s; void run(){ Service.create().save(1); } }",
            "Service.java": "package b; public class Service { public static Service create(){ return null; } public void save(int x){} }",
        }
    )
    assert len(calls(batch)) == 2 and all(
        c.resolution.status == "RESOLVED" for c in calls(batch)
    )


@pytest.mark.parametrize(
    "body,status",
    [
        ("m(unknown());", "AMBIGUOUS"),
        ("one(unknown());", "PARTIAL"),
        ("m(null);", "RESOLVED"),
        ("refs(null);", "AMBIGUOUS"),
        ('spread("a","b");', "PARTIAL"),
    ],
)
def test_unknown_null_and_varargs_are_conservative(body: str, status: str) -> None:
    batch = analyze(
        {
            "A.java": """class A { void m(int x){} void m(String x){} void one(int x){}
        void refs(String x){} void refs(Object x){} void spread(String... x){}
        void run(){ """
            + body
            + """ } }"""
        }
    )
    outer = calls(batch)[0]
    assert outer.resolution.status == status
    if status != "RESOLVED":
        assert outer.resolution.target is None


def test_external_import_is_preserved_without_global_edge() -> None:
    batch = analyze(
        {
            "A.java": "import external.Client; class A { Client client; void run(){ client.send(); } }"
        }
    )
    external = next(e for e in batch.entities if isinstance(e, ExternalReference))
    assert external.selector.qualified_name == "external.Client.send"
    assert (
        external.selector.parameter_type_names is None
        and external.resolution == "UNRESOLVED"
    )
    assert calls(batch)[0].resolution.status == "UNRESOLVED"
    assert any(
        isinstance(e, Relation) and e.relation_kind == RelationKind.EXTERNAL_DEPENDENCY
        for e in batch.entities
    )


@pytest.mark.parametrize(
    "text",
    [
        "class Base {} class A extends Base { void m(){} void run(){ m(); } }",
        "class A { void m(){} static void run(){ m(); } }",
        "class A { void m(){} void run(){ A.m(); } }",
        "class A { private void hidden(){} } class B { A a; void run(){ a.hidden(); } }",
    ],
)
def test_inheritance_static_and_access_limits_do_not_resolve(text: str) -> None:
    batch = analyze({"A.java": text})
    assert all(c.resolution.status != "RESOLVED" for c in calls(batch))


def test_profile_tracks_catalog_but_not_body_and_stale_input_rejected() -> None:
    a = source("A.java", "class A { void run(){ run(); } }")
    b = source("A.java", "// comment\nclass A { void run(){ int x=1; run(); } }")
    c = source("A.java", "class A { void run(int x){} }")
    analyzer = JavaCallAnalyzer((a,))
    assert analyzer.analysis_version == JavaCallAnalyzer((b,)).analysis_version
    assert analyzer.analysis_version != JavaCallAnalyzer((c,)).analysis_version
    with pytest.raises(ValueError, match="catalog"):
        asyncio.run(analyzer((b,)))


def test_call_occurrences_and_reference_relation_agree() -> None:
    batch = analyze({"A.java": "class A { void m(int x){} void run(){ m(1); } }"})
    occurrence = next(
        e
        for e in batch.entities
        if isinstance(e, Occurrence) and e.occurrence_kind == "CALL"
    )
    reference = next(
        e
        for e in batch.entities
        if isinstance(e, Relation)
        and e.source.id == occurrence.id
        and e.relation_kind == RelationKind.REFERENCES
    )
    assert (
        occurrence.resolution == "RESOLVED"
        and occurrence.target_symbol_id == reference.resolution.target.id
    )


def test_multiple_arguments_use_dominance_not_sum_or_declaration_order() -> None:
    batch = analyze(
        {
            "A.java": "class A { void m(int a,long b){} void m(long a,int b){} void run(){ m(1,1); } }"
        }
    )
    assert calls(batch)[0].resolution.status == "AMBIGUOUS"
    assert calls(batch)[0].resolution.target is None


def test_explicit_static_import_can_resolve_locally_or_stay_external() -> None:
    batch = analyze(
        {
            "A.java": "import static util.Helper.run; import static external.Helper.send; class A { void call(){ run(1); send(); } }",
            "Helper.java": "package util; public class Helper { public static void run(int x){} }",
        }
    )
    assert [c.resolution.status for c in calls(batch)] == ["RESOLVED", "UNRESOLVED"]
    assert (
        next(
            e for e in batch.entities if isinstance(e, ExternalReference)
        ).selector.qualified_name
        == "external.Helper.send"
    )


def test_generic_class_type_variables_and_wildcards_do_not_gain_exact_targets() -> None:
    generic = analyze({"A.java": "class A<T> { void m(T x){} void run(T x){ m(x); } }"})
    wildcard = analyze(
        {
            "A.java": 'import unknown.*; class A { void m(String x){} void run(){ m("x"); } }'
        }
    )
    assert calls(generic)[0].resolution.status == "PARTIAL"
    assert calls(wildcard)[0].resolution.status == "PARTIAL"


def test_same_package_type_wins_over_unrelated_default_package_name() -> None:
    batch = analyze(
        {
            "A.java": "package p; class A { Service s; void run(){ s.go(); } }",
            "Service.java": "package p; class Service { void go(){} }",
            "Other.java": "class Service { void go(){} }",
        }
    )
    symbols = {e.id: e for e in batch.entities if isinstance(e, Symbol)}
    assert (
        symbols[calls(batch)[0].resolution.target.id].qualified_name == "p.Service.go"
    )


def test_local_type_shadow_is_not_resolved_as_same_named_member_type() -> None:
    batch = analyze(
        {
            "A.java": "class A { static class Local { void go(){} } void run(){ class Local { void go(){} } Local x=new Local(); x.go(); } }"
        }
    )
    assert calls(batch)[0].resolution.status != "RESOLVED"


def test_generic_method_array_type_variable_does_not_bind_same_named_class() -> None:
    batch = analyze(
        {
            "A.java": "class T {} class A { void m(T[][] x){} <T> void run(T[][] x){ m(x); } }"
        }
    )
    assert calls(batch)[0].resolution.status == "PARTIAL"
