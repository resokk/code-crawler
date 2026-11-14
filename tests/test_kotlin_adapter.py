import asyncio
import hashlib
from uuid import UUID

REPO = UUID("00000000-0000-0000-0000-000000000001")

import pytest

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.kotlin_adapter import KotlinSourceAdapter
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.ucm import (
    DataAccess,
    EntityType,
    ExternalReference,
    Occurrence,
    Relation,
    RelationKind,
    SourceAnalysis,
    SourceFile,
    SqlConstruction,
    SqlExecute,
    Symbol,
    logical_id,
)


def source(text, path="a.kt"):
    content = text.encode() if isinstance(text, str) else text
    return SourceInput(
        SourceFile(
            repository_id=str(REPO),
            logical_key=path,
            id=logical_id(str(REPO), EntityType.SOURCE_FILE, path),
            name=path,
            path=path,
            language="java" if path.endswith(".java") else "kotlin",
            content_sha256=hashlib.sha256(content).hexdigest(),
        ),
        content,
    )


def analyze(*sources):
    async def run():
        registry = AdapterRegistry(
            (KotlinSourceAdapter(), JavaSourceAdapter(profile="symbols"))
        )
        prepared = await registry.prepare(sources)
        result = await prepared(sources)
        entities = tuple(e for f in result for e in f.entities)
        UcmBatch(repository_id=REPO, entities=(*(s.file for s in sources), *entities))
        return entities

    return asyncio.run(run())


def calls(entities):
    return [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]


def test_overloads_and_exact_calls():
    entities = analyze(
        source(
            'package demo\nfun find(x: Int) = x\nfun find(x: String) = x\nfun run() { find(1); find("a"); find(unknown) }\n'
        )
    )
    methods = [e for e in entities if isinstance(e, Symbol) and e.name == "find"]
    assert len(methods) == 2
    assert len({m.id for m in methods}) == 2
    assert len(calls(entities)) == 2
    assert any(isinstance(e, ExternalReference) and e.name == "find" for e in entities)
    assert all(e.evidence for e in calls(entities))


def test_extension_receiver_nullable_generic_and_unknown():
    entities = analyze(
        source(
            "fun String.ext(x: Int): String = this\nfun run(s: String, n: String?) { s.ext(1); n.ext(1); unknown.ext(1) }\nfun <T> generic(x: List<T?>): T? = null\n"
        )
    )
    assert len(calls(entities)) == 1
    extension = next(e for e in entities if isinstance(e, Symbol) and e.name == "ext")
    assert "receiver:String" in extension.owner_key
    generic = next(e for e in entities if isinstance(e, Symbol) and e.name == "generic")
    assert generic.signature.parameter_types[0].name == "List<T?>"


def test_java_static_canonical_target():
    entities = analyze(
        source(
            "package demo; public class Helper { public static int twice(int x) { return x+x; } }",
            "Helper.java",
        ),
        source("package demo\nimport demo.Helper\nfun run() { Helper.twice(1) }\n"),
    )
    target = next(e for e in entities if isinstance(e, Symbol) and e.name == "twice")
    assert len(calls(entities)) == 1
    assert calls(entities)[0].resolution.target.id == target.id


def test_script_and_invalid_bytes():
    entities = analyze(source("unknown.dynamic()\n", "build.kts"))
    report = next(e for e in entities if isinstance(e, SourceAnalysis))
    assert report.diagnostics[0].code == "kotlin.SCRIPT_PARTIAL"
    assert all(c.status == "PARTIAL" for c in report.capabilities)
    assert not calls(entities)
    assert any(isinstance(e, ExternalReference) for e in entities)
    entities = analyze(source(b"\xff"))
    assert not any(isinstance(e, Symbol) for e in entities)
    assert next(e for e in entities if isinstance(e, SourceAnalysis)).diagnostics


def test_sql_explicit_type_and_unknown_api():
    entities = analyze(
        source(
            'import java.sql.Statement\nfun run(db: Statement) { val q = "select id from users"; db.executeQuery(q) }\n'
        )
    )
    assert any(isinstance(e, SqlConstruction) for e in entities)
    assert any(isinstance(e, SqlExecute) for e in entities)
    assert any(isinstance(e, DataAccess) and e.object_kind == "TABLE" for e in entities)
    entities = analyze(
        source('fun run(db: Unknown) { db.executeQuery("select id from users") }\n')
    )
    assert not any(isinstance(e, SqlExecute) for e in entities)


def test_unicode_coordinates_and_determinism():
    src = source("fun имя(x: Int) = x\nfun run() { имя(1) }\n")
    first, second = analyze(src), analyze(src)
    assert first == second
    occurrence = next(
        e
        for e in first
        if isinstance(e, Occurrence) and e.name == "имя" and e.occurrence_kind == "CALL"
    )
    assert (
        occurrence.source_range.end.byte_column
        - occurrence.source_range.start.byte_column
        == 6
    )


@pytest.mark.parametrize("code", ["fun f( {", 'fun run() { "unterminated }'])
def test_parse_failure(code):
    entities = analyze(source(code))
    assert next(e for e in entities if isinstance(e, SourceAnalysis)).diagnostics
    assert not any(isinstance(e, Symbol) for e in entities)


def test_missing_import_and_ambiguous_catalog_do_not_guess():
    assert not calls(
        analyze(
            source("package first\nfun String.ext() {}\n", "lib.kt"),
            source('package second\nfun run() { "x".ext() }\n'),
        )
    )
    entities = analyze(
        source("package p\nfun f(x: Int) {}\n", "one.kt"),
        source("package p\nfun f(x: Int) {}\n", "two.kt"),
        source("package p\nfun run() { f(1) }\n"),
    )
    assert not calls(entities)


def test_java_private_instance_and_shadowed_type_are_deferred():
    java = source(
        "package demo; public class Helper { private static int hidden(int x) { return x; } public int instance(int x) { return x; } public static int twice(int x) { return x; } }",
        "Helper.java",
    )
    entities = analyze(
        java,
        source(
            "import demo.Helper\nfun run(Helper: Unknown) { Helper.hidden(1); Helper.instance(1); Helper.twice(1) }\n"
        ),
    )
    assert not calls(entities)


@pytest.mark.parametrize("argument", ['"select $table"', '"select ${table}"', "q"])
def test_dynamic_sql_never_becomes_static(argument):
    entities = analyze(
        source(
            'import java.sql.Statement\nfun run(db: Statement) { var q = "select id from users"; db.executeQuery('
            + argument
            + ") }\n"
        )
    )
    assert not any(isinstance(e, SqlExecute) for e in entities)
    assert any(
        d.code == "kotlin.SQL_DYNAMIC"
        for e in entities
        if isinstance(e, SourceAnalysis)
        for d in e.diagnostics
    )


def test_sql_literal_concatenation_and_prepare_is_not_execution():
    entities = analyze(
        source(
            'import java.sql.Connection\nfun run(db: Connection) { val prefix = "select id "; val q = prefix + "from users"; db.prepareStatement(q) }\n'
        )
    )
    assert any(
        isinstance(e, SqlConstruction) and e.variants[0].text == "select id from users"
        for e in entities
    )
    assert not any(isinstance(e, SqlExecute) for e in entities)


def test_interfaces_objects_constructors_and_lexical_reads():
    entities = analyze(
        source(
            'package p\ninterface I {\n fun get(x: String?): String?\n}\nobject O {\n val count: Int = 1\n}\nclass A(val name: String) {\n constructor(n: Int): this("x") {}\n fun read(x: Int) = x\n}\n'
        )
    )
    symbols = [e for e in entities if isinstance(e, Symbol)]
    assert {"I", "O", "A", "name", "count", "get", "read"} <= {s.name for s in symbols}
    assert len([s for s in symbols if s.symbol_kind == "CONSTRUCTOR"]) == 2
    assert any(
        isinstance(e, Occurrence) and e.name == "x" and e.occurrence_kind == "READ"
        for e in entities
    )


def test_catalog_addition_and_adapter_fingerprint_invalidate():
    async def run():
        registry = AdapterRegistry((KotlinSourceAdapter(),))
        a = source("fun run() { missing(1) }\n")
        first = await registry.prepare((a,))
        second = await registry.prepare(
            (a, source("fun missing(x: Int) {}\n", "new.kt"))
        )
        assert first.analysis_version != second.analysis_version
        assert first.scopes[0].fingerprint != second.scopes[0].fingerprint

    asyncio.run(run())


def test_descriptor_version_changes_adapter_scope():
    class NextKotlin(KotlinSourceAdapter):
        @property
        def descriptor(self):
            return super().descriptor.model_copy(update={"version": "2"})

    async def run():
        src = source("fun run() {}\n")
        first = await AdapterRegistry((KotlinSourceAdapter(),)).prepare((src,))
        second = await AdapterRegistry((NextKotlin(),)).prepare((src,))
        assert first.scopes[0].fingerprint != second.scopes[0].fingerprint
        assert first.analysis_version != second.analysis_version

    asyncio.run(run())


def test_interface_dispatch_remains_unresolved():
    entities = analyze(
        source("interface I {\n fun f(x: Int)\n fun run() { f(1) }\n}\n")
    )
    assert not calls(entities)
