import asyncio
import hashlib

import pytest

from code_crawler.groovy_adapter import GroovySourceAdapter
from code_crawler.groovy_parse import parse_groovy
from code_crawler.groovy_ucm import extract_groovy
from code_crawler.incremental import SourceInput
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.ucm import (
    DataAccess,
    EntityType,
    ExternalReference,
    Occurrence,
    SourceAnalysis,
    SourceFile,
    SqlConstruction,
    SqlExecute,
    SqlStatement,
    Symbol,
    logical_id,
)


def source(text, path="a.groovy"):
    content = text.encode() if isinstance(text, str) else text
    return SourceInput(
        SourceFile(
            repository_id="r",
            logical_key=path,
            id=logical_id("r", EntityType.SOURCE_FILE, path),
            name=path,
            path=path,
            language="groovy",
            content_sha256=hashlib.sha256(content).hexdigest(),
        ),
        content,
    )


def facts(text, cls):
    result = extract_groovy(source(text))
    assert not result.diagnostics, result.diagnostics
    return [e for e in result.analysis.entities if isinstance(e, cls)]


def variants(text):
    return [v for c in facts(text, SqlConstruction) for v in c.variants]


def test_unicode_source_coordinates():
    symbols = facts('def имя = "é"\nprintln имя', Symbol)
    symbol = next(s for s in symbols if s.name == "имя")
    assert symbol.source_range.start.byte_column == 4
    assert symbol.source_range.end.byte_column == 10
    read = next(
        o
        for o in facts('def имя = "é"\nprintln имя', Occurrence)
        if o.name == "имя" and o.occurrence_kind == "READ"
    )
    assert read.target_symbol_id == symbol.id
    assert read.source_range.start.line == 2
    assert read.source_range.end.byte_column == 14


@pytest.mark.parametrize(
    "text", [b"\xff", b"class {", b'def q = "unterminated', b"def n = 09"]
)
def test_invalid_source_has_only_diagnostics(text, capsys):
    result = extract_groovy(source(text))
    assert result.diagnostics
    assert not result.analysis.entities
    assert all(c.status == "UNSUPPORTED" for c in result.capabilities[1:])
    assert not capsys.readouterr().err


def test_methods_signatures_constructor_and_script():
    symbols = facts(
        "class A { A(String x) {}\n def find(int n, String... args) {} }\ndef top(x) {}",
        Symbol,
    )
    constructor = next(s for s in symbols if s.symbol_kind == "CONSTRUCTOR")
    assert constructor.name == "A"
    method = next(s for s in symbols if s.name == "find")
    assert [t.name for t in method.signature.parameter_types] == ["int", "String[]"]
    top = next(s for s in symbols if s.name == "top")
    assert top.signature.parameter_types[0].name == "groovy.dynamic"
    assert top.qualified_name == "<script:a.groovy>.top"


def test_lexical_shadowing_and_property_names():
    text = "class A { def x; def f(x) { { y -> println x; println y }; other.x; println x } }"
    symbols = facts(text, Symbol)
    parameter = next(
        s for s in symbols if s.name == "x" and s.symbol_kind == "PARAMETER"
    )
    refs = facts(text, Occurrence)
    assert all(
        r.target_symbol_id == parameter.id
        for r in refs
        if r.name == "x" and r.occurrence_kind == "READ"
    )
    prop = next(r for r in refs if r.name == "x" and r.occurrence_kind == "REFERENCE")
    assert prop.resolution == "UNRESOLVED"
    assert (
        next(
            r for r in refs if r.name == "y" and r.occurrence_kind == "READ"
        ).resolution
        == "RESOLVED"
    )


def test_script_locals_not_captured_by_methods():
    text = 'def x = "users"\ndef f() { println x }\nclass C { def f() { println x } }'
    assert all(
        o.resolution == "UNRESOLVED"
        for o in facts(text, Occurrence)
        if o.name == "x" and o.occurrence_kind == "READ"
    )


@pytest.mark.parametrize(
    "literal",
    [
        "'select id from users'",
        '"select id from users"',
        "'''select id\nfrom users'''",
        '"""select id\nfrom users"""',
        "/select id from users/",
        "$/select id from users/$",
    ],
)
def test_string_forms_and_semantic_access(literal):
    text = "def q = " + literal
    recovered = variants(text)
    assert len(recovered) == 1
    assert not recovered[0].partial
    assert any(
        a.object_kind == "TABLE" and a.access_kind == "READ"
        for a in facts(text, DataAccess)
    )
    assert not facts(text, SqlExecute)


def test_concat_and_constant_interpolation():
    text = 'class A { final String T="users"; def f() { def column="id"; def q="select $column from " + T } }'
    recovered = variants(text)
    assert len(recovered) == 1
    assert recovered[0].text == "select id from users"
    assert not recovered[0].partial


def test_parameter_shadows_final_field():
    v = variants(
        'class A { final String T="users"; def f(T) { def q="select id from $T" } }'
    )[0]
    assert v.partial and "__unknown__" in v.text
    assert any(f.kind == "DYNAMIC" for f in v.fragments)


def test_constants_do_not_leak_between_classes():
    v = variants(
        'class A { final T="users" }\nclass B { final T="orders"; def f() { def q="select id from $T" } }'
    )[0]
    assert v.text == "select id from orders"


@pytest.mark.parametrize(
    "interpolation", ["$user.name", "${makeTable()}", '${-> "users"}']
)
def test_dynamic_gstrings_are_partial(interpolation):
    text = 'def q="select id from ' + interpolation + '"'
    assert variants(text)[0].partial
    assert not facts(text, DataAccess)
    assert facts(text, SqlStatement)[0].parse_status == "PARTIAL"


def test_mutation_does_not_reuse_stale_constant():
    v = variants('def t="users"; if (flag) { t="orders" }; def q="select id from $t"')[
        0
    ]
    assert v.partial


def test_numeric_addition_not_string_concatenation():
    v = variants('def q="select id from users where id=" + (1+2)')[0]
    assert "12" not in v.text
    assert v.partial


def test_literal_unknown_marker_remains_static():
    v = variants("def q='select id from __unknown__'")[0]
    assert not v.partial
    assert all(f.kind == "STATIC" for f in v.fragments)


def test_calls_are_unresolved_and_do_not_imply_sql_execution():
    text = 'def f() {}\nf()\nsql.execute("delete from users")'
    assert facts(text, ExternalReference)
    assert all(
        o.resolution == "UNRESOLVED"
        for o in facts(text, Occurrence)
        if o.occurrence_kind == "CALL"
    )
    assert not facts(text, SqlExecute)


def test_duplicate_signatures_fail_closed():
    result = extract_groovy(source("class A { def f(x) {}\ndef f(y) {} }"))
    assert not result.analysis.entities
    assert result.diagnostics[0].code == "groovy.EXTRACTION_ERROR"


def test_registry_routes_and_reports():
    async def run():
        registry = AdapterRegistry((GroovySourceAdapter(),))
        assert registry.route("build.gradle").key == "groovy"
        assert registry.route("build.gradle.kts") is None
        src = source('def q="select id from users"')
        prepared = await registry.prepare((src,))
        results = await prepared((src,))
        report = next(e for e in results[0].entities if isinstance(e, SourceAnalysis))
        assert report.adapter_key == "groovy"
        assert report.capabilities[0].status in ("COMPLETE", "PARTIAL")

    asyncio.run(run())


def test_dialect_changes_analysis_version():
    async def run():
        a = await GroovySourceAdapter().prepare(())
        b = await GroovySourceAdapter(dialect="mysql").prepare(())
        assert a.analysis_version != b.analysis_version

    asyncio.run(run())


def test_parser_records_prediction_mode():
    result = parse_groovy(source('println "ok"'))
    assert not result.diagnostics
    assert result.prediction_mode in ("SLL", "LL")


@pytest.mark.parametrize(
    "mutation", ["t++", "++t", 't += "orders"', 'while(flag) { t="orders" }']
)
def test_all_mutations_invalidate_recovery(mutation):
    v = variants('def t="users"; ' + mutation + '; def q="select id from $t"')[0]
    assert v.partial


def test_interpolation_statement_not_treated_as_return_value():
    v = variants("def q=\"select id from ${def t='users'}\"")[0]
    assert v.partial


def test_unary_expression_not_silently_removed():
    v = variants('def q="select id from users where id=${-1}"')[0]
    assert v.partial or v.text.endswith("=-1")


def test_implicit_closure_it_does_not_capture_outer_it():
    v = variants('def it="users"; rows.each { def q="select id from $it" }')[0]
    assert v.partial


def test_dynamic_registry_output_is_valid():
    async def run():
        src = source('class A { def f(x) { def q="select id from $x"; sql.rows(q) } }')
        prepared = await AdapterRegistry((GroovySourceAdapter(),)).prepare((src,))
        assert await prepared((src,))

    asyncio.run(run())


def test_loop_binding_does_not_resolve_to_outer_constant():
    assert variants('def t="users"; for (t in tables) { def q="select id from $t" }')[
        0
    ].partial


def test_final_word_in_mutable_field_string_is_not_modifier():
    assert variants(
        'class A { String T="final_table"; def f() { def q="select id from $T" } }'
    )[0].partial


def test_tuple_declaration_reports_unsupported_extraction():
    result = extract_groovy(source("def (x,y)=[1,2]"))
    assert result.diagnostics
    assert not result.analysis.entities
