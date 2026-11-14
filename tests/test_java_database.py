import asyncio
import hashlib
from uuid import UUID

from code_crawler.database_resolution import ConnectionAssignment, ConnectionContext
from code_crawler.database_schema import (
    ColumnDefinition,
    SchemaDefinition,
    SchemaImport,
    TableDefinition,
)
from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_database import JavaDatabaseAnalyzer
from code_crawler.java_lineage import JavaLineageAnalyzer
from code_crawler.ucm import (
    DatabaseAccess,
    DatabaseContext,
    DatabaseObject,
    EntityType,
    Relation,
    RelationKind,
    SourceFile,
    Symbol,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")


def document(key: str = "prod", version: str = "v1") -> SchemaImport:
    return SchemaImport(
        database_key=key,
        version_key=version,
        dialect="postgres",
        catalog_name="app",
        schemas=(
            SchemaDefinition(
                name="public",
                tables=(
                    TableDefinition(
                        name="users",
                        columns=(
                            ColumnDefinition(
                                name="id", ordinal=1, data_type="int", nullable=False
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def analyze(
    body: str,
    bindings: dict[str, str] | None = None,
    texts: tuple[str, ...] | None = None,
) -> UcmBatch:
    contents = texts or (
        "import java.sql.Connection;import java.sql.PreparedStatement;class A{void m(Connection c,Connection other,int id){"
        + body
        + "}}",
    )
    sources = []
    for index, text in enumerate(contents):
        name = f"A{index}.java"
        content = text.encode()
        file = SourceFile(
            repository_id=str(REPO),
            logical_key=name,
            id=logical_id(str(REPO), EntityType.SOURCE_FILE, name),
            name=name,
            path=name,
            language="java",
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        sources.append(SourceInput(file, content))
    sources = tuple(sources)
    base = JavaLineageAnalyzer(sources)
    assignments = []
    for file in base.files.values():
        for symbol in file.result.analysis.entities:
            if (
                isinstance(symbol, Symbol)
                and symbol.symbol_kind == "PARAMETER"
                and symbol.name in (bindings or {})
            ):
                key = bindings[symbol.name]
                assignments.append(
                    ConnectionAssignment(
                        symbol_key=symbol.logical_key,
                        context=ConnectionContext(
                            connection_key=symbol.name,
                            database_key=key,
                            version_key="v1",
                            search_path=("public",),
                        ),
                    )
                )
    schemas = tuple(document(key) for key in sorted(set((bindings or {}).values())))
    results = asyncio.run(
        JavaDatabaseAnalyzer(sources, schemas, tuple(assignments))(sources)
    )
    batch = UcmBatch(
        repository_id=REPO,
        entities=tuple(s.file for s in sources)
        + tuple(e for r in results for e in r.entities),
    )
    assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
    return batch


def resolutions(batch: UcmBatch) -> list[Relation]:
    return [
        e
        for e in batch.entities
        if isinstance(e, Relation)
        and e.relation_kind == RelationKind.RESOLVES_DATABASE_OBJECT
    ]


def test_prepared_execution_resolves_table_and_column() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("select id from users");p.executeQuery();',
        {"c": "prod"},
    )
    assert resolutions(batch) and all(
        r.resolution.status == "RESOLVED" for r in resolutions(batch)
    )
    assert {e.object_kind for e in batch.entities if isinstance(e, DatabaseObject)} == {
        "TABLE",
        "COLUMN",
    }


def test_no_context_does_not_guess_a_database() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("select id from users");p.executeQuery();'
    )
    assert resolutions(batch) and all(
        r.resolution.status == "UNRESOLVED" for r in resolutions(batch)
    )
    assert not any(isinstance(e, DatabaseObject) for e in batch.entities)


def test_unused_sql_has_unknown_context() -> None:
    batch = analyze('String q="select id from users";', {"c": "prod"})
    assert all(r.resolution.status == "UNRESOLVED" for r in resolutions(batch))
    assert all(
        e.execution_id is None for e in batch.entities if isinstance(e, DatabaseAccess)
    )


def test_statement_and_prepared_aliases_keep_connection_origin() -> None:
    batch = analyze(
        'var s=c.createStatement();s.execute("select id from users");PreparedStatement p=c.prepareStatement("select id from users");PreparedStatement alias=p;alias.execute();',
        {"c": "prod"},
    )
    assert resolutions(batch) and all(
        r.resolution.status == "RESOLVED" for r in resolutions(batch)
    )


def test_same_sql_in_different_databases_has_distinct_global_keys() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("select id from users");PreparedStatement q=other.prepareStatement("select id from users");p.execute();q.execute();',
        {"c": "prod", "other": "test"},
    )
    objects = [e for e in batch.entities if isinstance(e, DatabaseObject)]
    assert {e.database_key for e in objects} == {"prod", "test"}
    assert len({e.object_key for e in objects}) == len(objects)


def test_ambiguous_connection_branch_does_not_assert_definite_database() -> None:
    batch = analyze(
        'PreparedStatement p;if(id>0){p=c.prepareStatement("select id from users");}else{p=other.prepareStatement("select id from users");}p.execute();',
        {"c": "prod", "other": "test"},
    )
    assert resolutions(batch) and all(
        r.resolution.status == "PARTIAL" for r in resolutions(batch)
    )


def test_file_owned_projections_do_not_duplicate_entities_across_files() -> None:
    texts = tuple(
        "import java.sql.Connection;class "
        + name
        + ' {void m(Connection c){c.createStatement().execute("select id from users");}}'
        for name in ("A", "B")
    )
    batch = analyze("", {"c": "prod"}, texts)
    objects = [e for e in batch.entities if isinstance(e, DatabaseObject)]
    assert len(objects) > len({e.object_key for e in objects})
    assert len({e.id for e in objects}) == len(objects)
    assert len([e for e in batch.entities if isinstance(e, DatabaseContext)]) == 2
