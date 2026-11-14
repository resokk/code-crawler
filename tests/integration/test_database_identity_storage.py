import asyncio
import hashlib
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.database_resolution import ConnectionAssignment, ConnectionContext
from code_crawler.database_schema import (
    ColumnDefinition,
    SchemaDefinition,
    SchemaImport,
    TableDefinition,
    import_schema,
    introspect_schema,
    load_schema,
)
from code_crawler.incremental import SourceInput
from code_crawler.java_database import index_java_database
from code_crawler.java_lineage import JavaLineageAnalyzer
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import (
    DatabaseObject,
    EntityType,
    Relation,
    RelationKind,
    SourceFile,
    Symbol,
    logical_id,
)

pytestmark = pytest.mark.integration


async def migrate(conn: asyncpg.Connection) -> None:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")


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
                                name="id",
                                ordinal=1,
                                data_type="integer",
                                nullable=False,
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_schema_import_versions_idempotency_and_global_immutability(
    database_url: str,
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            first = document()
            assert await import_schema(conn, first) == first.fingerprint
            assert await import_schema(conn, first) == first.fingerprint
            assert (
                await load_schema(conn, "prod", "v1")
            ).fingerprint == first.fingerprint
            await import_schema(conn, document("test"))
            await import_schema(conn, document(version="v2"))
            assert (
                await conn.fetchval("SELECT count(*) FROM ucm_database_schema_versions")
                == 3
            )
            changed = first.model_copy(update={"coverage": "PARTIAL"})
            with pytest.raises(ValueError, match="immutable"):
                await import_schema(conn, changed)
            for query in (
                "UPDATE ucm_database_schema_versions SET coverage='PARTIAL' WHERE database_key='prod'",
                "DELETE FROM ucm_database_schema_objects",
                "TRUNCATE ucm_database_schema_objects CASCADE",
            ):
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(query)
            assert (
                await load_schema(conn, "prod", "v1")
            ).fingerprint == first.fingerprint
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_live_postgres_introspection_is_independent_and_preserves_empty_schema(
    database_url: str,
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await conn.execute(
                'CREATE SCHEMA "App"; CREATE SCHEMA empty_schema; CREATE TABLE "App"."Users" ("ID" integer PRIMARY KEY, name text);CREATE VIEW "App".user_view AS SELECT "ID" FROM "App"."Users"'
            )
            imported = await introspect_schema(conn, "external-postgres", "release-1")
            assert any(
                s.name == "empty_schema" and s.tables == () for s in imported.schemas
            )
            users = next(
                t
                for s in imported.schemas
                if s.name == "App"
                for t in s.tables
                if t.name == "Users"
            )
            assert users.columns[0].name == "ID" and users.columns[0].primary_key
            assert any(t.kind == "VIEW" for s in imported.schemas for t in s.tables)
            await migrate(conn)
            await import_schema(conn, imported)
            assert (
                await load_schema(conn, "external-postgres", "release-1")
            ).fingerprint == imported.fingerprint
            assert await conn.fetchval("SELECT count(*) FROM ucm_snapshots") == 0
            assert await conn.fetchval("SELECT count(*) FROM data_tables") == 0
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_database_projections_roundtrip_reuse_and_version_invalidation(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            await import_schema(conn, document())
            await import_schema(conn, document(version="v2"))
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "Database Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            content = b'import java.sql.Connection; class A {void m(Connection c){c.createStatement().execute("select id from users");}}'
            (tmp_path / "A.java").write_bytes(content)
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="database",
                    display_name="database",
                    source=str(tmp_path),
                ),
            )
            source = SourceFile(
                repository_id=str(repo),
                logical_key="A.java",
                id=logical_id(str(repo), EntityType.SOURCE_FILE, "A.java"),
                name="A.java",
                path="A.java",
                language="java",
                content_sha256=hashlib.sha256(content).hexdigest(),
            )
            analyzer = JavaLineageAnalyzer((SourceInput(source, content),))
            symbol = next(
                e
                for f in analyzer.files.values()
                for e in f.result.analysis.entities
                if isinstance(e, Symbol)
                and e.symbol_kind == "PARAMETER"
                and e.name == "c"
            )

            def assignment(version: str) -> tuple[ConnectionAssignment, ...]:
                return (
                    ConnectionAssignment(
                        symbol_key=symbol.logical_key,
                        context=ConnectionContext(
                            connection_key="primary",
                            database_key="prod",
                            version_key=version,
                            search_path=("public",),
                        ),
                    ),
                )

            first = await index_java_database(conn, repo, tmp_path, assignment("v1"))
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            assert any(
                isinstance(e, DatabaseObject) and e.object_kind == "COLUMN"
                for e in batch.entities
            )
            resolved = [
                e
                for e in batch.entities
                if isinstance(e, Relation)
                and e.relation_kind == RelationKind.RESOLVES_DATABASE_OBJECT
            ]
            assert resolved and all(e.resolution.status == "RESOLVED" for e in resolved)
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ucm_database_search_paths WHERE snapshot_id=$1",
                    first.snapshot_id,
                )
            reused = await index_java_database(conn, repo, tmp_path, assignment("v1"))
            assert reused.plan.reanalyze == () and reused.plan.reused == ("A.java",)
            await validate_snapshot(conn, reused.snapshot_id)
            restored = await load_snapshot_batch(conn, reused.snapshot_id)
            assert {e.id: e for e in restored.entities} == {
                e.id: e for e in batch.entities
            }
            changed = await index_java_database(conn, repo, tmp_path, assignment("v2"))
            assert changed.plan.reanalyze == ("A.java",)
            await validate_snapshot(conn, changed.snapshot_id)
            assert all(
                e.version_key == "v2"
                for e in (await load_snapshot_batch(conn, changed.snapshot_id)).entities
                if isinstance(e, DatabaseObject)
            )
            assert all(
                e.version_key == "v1"
                for e in (await load_snapshot_batch(conn, first.snapshot_id)).entities
                if isinstance(e, DatabaseObject)
            )
            corrupt = await index_java_database(conn, repo, tmp_path, assignment("v2"))
            await conn.execute(
                "UPDATE ucm_database_objects SET schema_name='wrong' WHERE snapshot_id=$1",
                corrupt.snapshot_id,
            )
            with pytest.raises(ValueError, match="global identity"):
                await validate_snapshot(conn, corrupt.snapshot_id)
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
        finally:
            await conn.close()

    asyncio.run(scenario())
