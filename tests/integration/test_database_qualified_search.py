import asyncio
import hashlib
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, search, snapshots
from code_crawler.database_resolution import ConnectionAssignment, ConnectionContext
from code_crawler.database_schema import (
    ColumnDefinition,
    SchemaDefinition,
    SchemaImport,
    TableDefinition,
    import_schema,
)
from code_crawler.incremental import SourceInput
from code_crawler.java_database import index_java_database
from code_crawler.java_symbols import extract
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import (
    DatabaseAccess,
    DatabaseObject,
    EntityType,
    Relation,
    RelationKind,
    SourceFile,
    Symbol,
    logical_id,
)

pytestmark = pytest.mark.integration

CODE = r"""import java.sql.Connection;
import java.sql.PreparedStatement;
class App {
 void run(Connection one, Connection two, Connection newer, Connection unknown, Connection partial) throws Exception {
   String sql="SELECT id FROM users";
   PreparedStatement a=one.prepareStatement(sql); a.executeQuery();
   PreparedStatement b=two.prepareStatement(sql); b.executeQuery();
   PreparedStatement c=newer.prepareStatement(sql); c.executeQuery();
   PreparedStatement u=unknown.prepareStatement(sql); u.executeQuery();
   PreparedStatement p=partial.prepareStatement(sql); p.executeQuery();
   PreparedStatement w=one.prepareStatement("UPDATE users SET id=1"); w.executeUpdate();
   PreparedStatement q=one.prepareStatement("SELECT \"ID\" FROM \"Users\""); q.executeQuery();
   PreparedStatement j=one.prepareStatement("SELECT id FROM public.users"); j.executeQuery();
 }
}"""


def manifest(key, version="v1", *, partial=False, extra_tables=()):
    return SchemaImport(
        database_key=key,
        version_key=version,
        dialect="postgres",
        catalog_name="app",
        coverage="PARTIAL" if partial else "COMPLETE",
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
                    TableDefinition(
                        name="Users",
                        columns=(
                            ColumnDefinition(
                                name="ID", ordinal=1, data_type="int", nullable=False
                            ),
                        ),
                    ),
                    *extra_tables,
                ),
            ),
        ),
    )


async def migrate(conn, *, before_index=False):
    for name in await db.begin_migration(conn, init=True):
        if not before_index or name < "0030_database_qualified_search.sql":
            await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")


async def setup(
    conn, root, key="app", *, create_schema=True, before_index=False, extra_tables=()
):
    if create_schema:
        await migrate(conn, before_index=before_index)
        for doc in (
            manifest("a", extra_tables=extra_tables),
            manifest("b"),
            manifest("a", "v2"),
            manifest("p", partial=True),
        ):
            await import_schema(conn, doc)
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Database Search Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    (root / "App.java").write_text(CODE)
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    repo = await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key=key, display_name=key, source=str(root)
        ),
    )
    content = CODE.encode()
    file = SourceFile(
        repository_id=str(repo),
        logical_key="App.java",
        id=logical_id(str(repo), EntityType.SOURCE_FILE, "App.java"),
        name="App.java",
        path="App.java",
        language="java",
        content_sha256=hashlib.sha256(content).hexdigest(),
    )
    params = {
        s.name: s
        for s in extract(SourceInput(file, content)).declared
        if isinstance(s, Symbol) and s.symbol_kind == "PARAMETER"
    }

    def assignments(version="v1"):
        return tuple(
            ConnectionAssignment(
                symbol_key=params[name].logical_key,
                context=ConnectionContext(
                    connection_key=name,
                    database_key=database,
                    version_key=v,
                    search_path=("missing", "public")
                    if name == "partial"
                    else ("public",),
                ),
            )
            for name, database, v in (
                ("one", "a", version),
                ("two", "b", "v1"),
                ("newer", "a", "v2"),
                ("partial", "p", "v1"),
            )
        )

    result = await index_java_database(conn, repo, root, assignments())
    await validate_snapshot(conn, result.snapshot_id)
    await publish_snapshot(conn, repo, result.snapshot_id, expected_snapshot_id=None)
    return repo, result, assignments


async def exact(conn, key="app", table="users", **options):
    return await search.find_table_readers(
        conn,
        key,
        table,
        mode="RESOLVED_DATABASE_OBJECT",
        database_key="a",
        schema_version_key="v1",
        **options,
    )


def test_database_modes_versions_quoted_names_scope_and_provenance(
    database_url: str, tmp_path: Path
):
    async def run():
        conn = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        try:
            repo, first, assignments = await setup(conn, tmp_path)
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            syntactic = await search.find_table_readers(conn, "app", "users")
            assert syntactic["mode"] == "SYNTACTIC_NAME"
            assert len(syntactic["items"]) > len((await exact(conn))["items"])
            assert any(i["executions"] for i in syntactic["items"])
            selected = await exact(conn)
            assert selected["items"] and selected["mode"] == "RESOLVED_DATABASE_OBJECT"
            assert selected["coverage"]["status"] == "PARTIAL"
            assert set(selected["coverage"]["excluded_resolutions"]) == {
                "UNRESOLVED",
                "PARTIAL",
                "AMBIGUOUS",
            }
            da = {e.id: e for e in batch.entities if isinstance(e, DatabaseAccess)}
            for item in selected["items"]:
                physical = item["database_object"]
                assert (
                    physical["database_key"],
                    physical["version_key"],
                    physical["table_name"],
                ) == ("a", "v1", "users")
                assert item["database_relation"]["resolution"] == "RESOLVED"
                assert item["target_resolution"] == "RESOLVED"
                assert item["discovery_status"] == "FOUND"
                assert item["execution_link_status"] == "INFERRED"
                assert item["access_relations"]
                assert all(
                    e["relation"]["certainty"] == "INFERRED" and e["sink_relations"]
                    for e in item["executions"]
                )
                assert (
                    item["database_relation"]["evidence"]
                    and item["database_relation"]["coverage"]
                )
                assert item["database_context"]["connection_key"] == "one"
                assert {e["id"] for e in item["executions"]} == {
                    da[item["database_access_id"]].execution_id
                }
            excluded = {
                r.source.id
                for r in batch.entities
                if isinstance(r, Relation)
                and r.relation_kind == RelationKind.RESOLVES_DATABASE_OBJECT
                and r.resolution.status != "RESOLVED"
            }
            assert excluded and not excluded & {
                i["database_access_id"] for i in selected["items"]
            }
            assert any(
                isinstance(r, Relation)
                and r.relation_kind == RelationKind.RESOLVES_DATABASE_OBJECT
                and r.resolution.status == "PARTIAL"
                for r in batch.entities
            )
            target = selected["items"][0]["database_object"]["database_object_id"]
            by_id = await search.find_table_readers(
                conn, "app", mode="RESOLVED_DATABASE_OBJECT", database_object_id=target
            )
            assert by_id["items"] == selected["items"]
            quoted = await exact(conn, table="Users", column="ID")
            assert quoted["items"] and all(
                i["database_object"]["table_name"] == "Users" for i in quoted["items"]
            )
            assert not (await exact(conn, table="Users", column="id"))["items"]
            assert not (await exact(conn, table="USERS"))["items"]
            column = await exact(conn, column="id")
            assert column["items"] and all(
                i["object_kind"] == "COLUMN" for i in column["items"]
            )
            column_id = column["items"][0]["database_object"]["database_object_id"]
            assert (
                await search.find_table_readers(
                    conn,
                    "app",
                    mode="RESOLVED_DATABASE_OBJECT",
                    database_object_id=column_id,
                )
            )["items"] == column["items"]
            for dbkey, version in (("a", "v2"), ("b", "v1")):
                page = await search.find_table_readers(
                    conn,
                    "app",
                    "users",
                    mode="RESOLVED_DATABASE_OBJECT",
                    database_key=dbkey,
                    schema_version_key=version,
                )
                assert page["items"] and all(
                    (
                        i["database_object"]["database_key"],
                        i["database_object"]["version_key"],
                    )
                    == (dbkey, version)
                    for i in page["items"]
                )
            assert not (
                await search.find_table_readers(
                    conn,
                    "app",
                    "users",
                    mode="RESOLVED_DATABASE_OBJECT",
                    database_key="p",
                    schema_version_key="v1",
                )
            )["items"]
            partial_object = next(
                e
                for e in batch.entities
                if isinstance(e, DatabaseObject)
                and e.database_key == "p"
                and e.object_kind == "TABLE"
            )
            assert not (
                await search.find_table_readers(
                    conn,
                    "app",
                    mode="RESOLVED_DATABASE_OBJECT",
                    database_object_id=partial_object.id,
                )
            )["items"]
            writes = await search.find_table_writers(
                conn,
                "app",
                "users",
                mode="RESOLVED_DATABASE_OBJECT",
                database_key="a",
                schema_version_key="v1",
            )
            assert writes["items"] and all(
                i["access_kind"] == "UPDATE" for i in writes["items"]
            )
            cut = await exact(conn, limit=1)
            assert cut["truncated"] and cut["items"] == selected["items"][:1]
            assert not (await exact(conn, table="absent"))["items"]
            before = await snapshots.published_snapshot(conn, repo)
            for opts in (
                {"table": "Users"},
                {"column": "id"},
                {"database_key": "b", "schema_version_key": "v1"},
                {"database_object_id": "ucm:" + "0" * 64},
            ):
                arguments = {"database_object_id": target, **opts}
                with pytest.raises(ValueError):
                    await search.find_table_readers(
                        conn, "app", mode="RESOLVED_DATABASE_OBJECT", **arguments
                    )
            assert (await snapshots.published_snapshot(conn, repo))["id"] == before[
                "id"
            ]
            # An authorized compound reader retains the old immutable snapshot during publication.
            async with other.transaction(isolation="repeatable_read", readonly=True):
                pinned = await exact(other)
                new = await index_java_database(conn, repo, tmp_path, assignments("v2"))
                await validate_snapshot(conn, new.snapshot_id)
                await publish_snapshot(
                    conn, repo, new.snapshot_id, expected_snapshot_id=first.snapshot_id
                )
                assert await exact(other) == pinned
            assert not (await exact(conn))["items"]
            with pytest.raises(ValueError, match="selected snapshot"):
                await search.find_table_readers(
                    conn,
                    "app",
                    mode="RESOLVED_DATABASE_OBJECT",
                    database_object_id=target,
                )
            root = tmp_path.with_name(tmp_path.name + "-b")
            root.mkdir()
            _, foreign, _ = await setup(conn, root, "other", create_schema=False)
            foreign_batch = await load_snapshot_batch(conn, foreign.snapshot_id)
            foreign_id = next(
                e.id for e in foreign_batch.entities if isinstance(e, DatabaseObject)
            )
            with pytest.raises(ValueError, match="selected snapshot"):
                await search.find_table_readers(
                    conn,
                    "app",
                    mode="RESOLVED_DATABASE_OBJECT",
                    database_object_id=foreign_id,
                )
        finally:
            await conn.close()
            await other.close()

    asyncio.run(run())


async def publish_fixture_batch(conn, repo, batch, previous):
    from code_crawler.ingestion import ingest_batch
    from code_crawler.source_evidence import archive_sources

    snap = await snapshots.create_snapshot(
        conn,
        repo,
        snapshots.SnapshotInput(
            commit_hash="fixture", source_fingerprint="a" * 64, dirty=False
        ),
    )
    await ingest_batch(conn, snap, batch)
    await archive_sources(
        conn,
        snap,
        tuple(
            SourceInput(e, CODE.encode())
            for e in batch.entities
            if isinstance(e, SourceFile)
        ),
        origin="PROVIDED_BYTES",
    )
    await validate_snapshot(conn, snap)
    await publish_snapshot(conn, repo, snap, expected_snapshot_id=previous)
    return snap


def test_ambiguous_database_binding_is_never_an_exact_match(
    database_url: str, tmp_path: Path
):
    from code_crawler.ingestion import UcmBatch
    from code_crawler.ucm import Certainty, EntityRef, Resolution

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo, first, _ = await setup(conn, tmp_path)
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            selected = await exact(conn)
            relation_id = selected["items"][0]["database_relation"]["relation_id"]
            target_objects = tuple(
                e
                for e in batch.entities
                if isinstance(e, DatabaseObject)
                and e.database_key == "a"
                and e.version_key == "v1"
                and e.object_kind == "TABLE"
            )
            assert len(target_objects) == 2
            candidates = tuple(
                EntityRef(id=e.id, entity_type=e.entity_type)
                for e in sorted(target_objects, key=lambda e: e.id)
            )
            entities = tuple(
                e.model_copy(
                    update={
                        "resolution": Resolution(
                            status="AMBIGUOUS",
                            candidates=candidates,
                            reason="fixture: two possible physical objects",
                        ),
                        "certainty": Certainty.UNKNOWN,
                    }
                )
                if e.id == relation_id
                else e
                for e in batch.entities
            )
            snapshot = await publish_fixture_batch(
                conn,
                repo,
                UcmBatch(repository_id=repo, entities=entities),
                first.snapshot_id,
            )
            result = await exact(conn)
            assert result["snapshot_id"] == str(snapshot)
            assert relation_id not in {
                i["database_relation"]["relation_id"] for i in result["items"]
            }
            assert "AMBIGUOUS" in result["coverage"]["excluded_resolutions"]
            syntactic = await search.find_table_readers(conn, "app", "users")
            assert selected["items"][0]["access_id"] in {
                i["access_id"] for i in syntactic["items"]
            }
        finally:
            await conn.close()

    asyncio.run(run())


def test_physical_search_plan_before_and_after_index(database_url: str, tmp_path: Path):
    import json
    import os
    import platform

    from code_crawler.database_schema import schema_objects
    from code_crawler.ingestion import UcmBatch
    from code_crawler.query_benchmark import RecordingConnection, plan_nodes

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            extra = tuple(TableDefinition(name=f"unrelated_{i}") for i in range(3000))
            repo, first, _ = await setup(
                conn, tmp_path, before_index=True, extra_tables=extra
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            file = next(e for e in batch.entities if isinstance(e, SourceFile))
            doc = manifest("a", extra_tables=extra)
            fingerprint = doc.fingerprint
            entities = list(batch.entities)
            seen = {e.id for e in entities}
            for obj in schema_objects(doc):
                if obj.object_kind != "TABLE":
                    continue
                key = json.dumps(
                    ["database.object", file.id, obj.object_key], separators=(",", ":")
                )
                identifier = logical_id(str(repo), EntityType.DATABASE_OBJECT, key)
                if identifier in seen:
                    continue
                entities.append(
                    DatabaseObject(
                        id=identifier,
                        repository_id=str(repo),
                        logical_key=key,
                        name=obj.table_name,
                        projection_file_id=file.id,
                        database_key="a",
                        version_key="v1",
                        schema_fingerprint=fingerprint,
                        object_key=obj.object_key,
                        object_kind=obj.object_kind,
                        catalog_name=doc.catalog_name,
                        schema_name=obj.schema_name,
                        table_name=obj.table_name,
                    )
                )
            snap = await publish_fixture_batch(
                conn,
                repo,
                UcmBatch(repository_id=repo, entities=tuple(entities)),
                first.snapshot_id,
            )
            await conn.execute("ANALYZE")

            async def measured():
                recording = RecordingConnection(conn)
                result = await exact(recording)
                query = next(
                    q
                    for q in recording.queries
                    if "FROM ucm_database_objects d " in q.sql
                )
                plan = json.loads(
                    await conn.fetchval(
                        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query.sql,
                        *query.arguments,
                    )
                )[0]
                return result, plan

            before, baseline = await measured()
            await db.apply_migration(conn, "0030_database_qualified_search.sql")
            await conn.execute("ANALYZE ucm_database_objects")
            after, indexed = await measured()
            assert before == after
            scans = list(plan_nodes(indexed["Plan"]))
            assert any(
                n.get("Index Name") == "ucm_database_objects_search_idx" for n in scans
            )
            report = {
                "baseline_sha": "12f0deb",
                "platform": platform.platform(),
                "postgres": await conn.fetchval("SELECT version()"),
                "projected_objects": await conn.fetchval(
                    "SELECT count(*) FROM ucm_database_objects WHERE snapshot_id=$1",
                    snap,
                ),
                "index_bytes": await conn.fetchval(
                    "SELECT pg_relation_size('ucm_database_objects_search_idx')"
                ),
                "before": baseline,
                "after": indexed,
            }
            if output := os.environ.get("A03_PLAN_REPORT"):
                await asyncio.to_thread(
                    Path(output).write_text,
                    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                )
        finally:
            await conn.close()

    asyncio.run(run())


def test_object_id_matches_all_file_projections_of_same_physical_object(
    database_url: str, tmp_path: Path
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo, first, assignments = await setup(conn, tmp_path)
            text = CODE.replace("class App", "class Other")
            content = text.encode()
            (tmp_path / "Other.java").write_text(text)
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "another projection", cwd=tmp_path)
            file = SourceFile(
                repository_id=str(repo),
                logical_key="Other.java",
                id=logical_id(str(repo), EntityType.SOURCE_FILE, "Other.java"),
                name="Other.java",
                path="Other.java",
                language="java",
                content_sha256=hashlib.sha256(content).hexdigest(),
            )
            symbol = next(
                e
                for e in extract(SourceInput(file, content)).declared
                if isinstance(e, Symbol)
                and e.symbol_kind == "PARAMETER"
                and e.name == "one"
            )
            extra = ConnectionAssignment(
                symbol_key=symbol.logical_key,
                context=ConnectionContext(
                    connection_key="one",
                    database_key="a",
                    version_key="v1",
                    search_path=("public",),
                ),
            )
            result = await index_java_database(
                conn, repo, tmp_path, (*assignments(), extra)
            )
            await validate_snapshot(conn, result.snapshot_id)
            await publish_snapshot(
                conn, repo, result.snapshot_id, expected_snapshot_id=first.snapshot_id
            )
            named = await exact(conn)
            ids = {i["database_object"]["database_object_id"] for i in named["items"]}
            assert len(ids) == 2
            assert (
                len({i["database_object"]["object_key"] for i in named["items"]}) == 1
            )
            for identifier in ids:
                by_id = await search.find_table_readers(
                    conn,
                    "app",
                    mode="RESOLVED_DATABASE_OBJECT",
                    database_object_id=identifier,
                )
                assert by_id["items"] == named["items"]
        finally:
            await conn.close()

    asyncio.run(run())


def test_mcp_physical_mode_is_authorized_and_keeps_errors_generic(
    database_url: str, tmp_path: Path, monkeypatch, mcp_credentials
):
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    from code_crawler.server import mcp

    monkeypatch.setenv("DATABASE_URL", database_url)

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo, first, _ = await setup(conn, tmp_path)
            selected = await exact(conn)
            target = selected["items"][0]["database_object"]["database_object_id"]
            async with Client(mcp) as client:
                physical = await client.call_tool(
                    "find_table_readers",
                    {
                        "repository_key": "app",
                        "mode": "RESOLVED_DATABASE_OBJECT",
                        "database_object_id": target,
                    },
                )
                assert physical.data["items"] == selected["items"]
                named = await client.call_tool(
                    "find_table_writers",
                    {
                        "repository_key": "app",
                        "mode": "RESOLVED_DATABASE_OBJECT",
                        "database_key": "a",
                        "schema_version_key": "v1",
                        "table": "users",
                    },
                )
                assert named.data["items"]
                with pytest.raises(ToolError, match="access denied"):
                    await client.call_tool(
                        "find_table_readers",
                        {
                            "repository_key": "other",
                            "mode": "RESOLVED_DATABASE_OBJECT",
                            "database_object_id": target,
                        },
                    )
                with pytest.raises(ToolError, match="query failed") as error:
                    await client.call_tool(
                        "find_table_readers",
                        {
                            "repository_key": "app",
                            "mode": "RESOLVED_DATABASE_OBJECT",
                            "database_key": "private-database",
                            "schema_version_key": "v1",
                            "database_object_id": target,
                        },
                    )
                assert "private-database" not in str(error.value) and target not in str(
                    error.value
                )
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
        finally:
            await conn.close()

    asyncio.run(run())
