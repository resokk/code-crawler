import asyncio
import hashlib
from pathlib import Path
from uuid import UUID

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
)
from code_crawler.incremental import SourceInput
from code_crawler.java_orm import JavaOrmAnalyzer, index_java_orm
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import (
    EntityType,
    OrmMapping,
    OrmOperation,
    Relation,
    RelationKind,
    SourceFile,
    SqlExecute,
    Symbol,
    logical_id,
)

pytestmark = pytest.mark.integration


async def setup(
    conn: asyncpg.Connection, root: Path
) -> tuple[UUID, tuple[ConnectionAssignment, ...]]:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    document = SchemaImport(
        database_key="orders",
        version_key="v1",
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
    await import_schema(conn, document)
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "ORM Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    files = {
        "User.java": 'import jakarta.persistence.*; @Entity @Table(name="users") @NamedQuery(name="User.all",query="select u from User u") class User {@Id int id;}',
        "Dao.java": 'import jakarta.persistence.*; class Dao {void m(EntityManager em,User u){em.persist(u);em.createNamedQuery("User.all").getResultList();em.createNativeQuery("select id from users").getResultList();}}',
    }
    for path, text in files.items():
        (root / path).write_text(text)
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    repo = await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="orm", display_name="orm", source=str(root)
        ),
    )
    sources = []
    for path, text in files.items():
        content = text.encode()
        file = SourceFile(
            repository_id=str(repo),
            logical_key=path,
            id=logical_id(str(repo), EntityType.SOURCE_FILE, path),
            name=path,
            path=path,
            language="java",
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        sources.append(SourceInput(file, content))
    analyzer = JavaOrmAnalyzer(tuple(sources))
    symbol = next(
        e
        for f in analyzer.files.values()
        for e in f.result.analysis.entities
        if isinstance(e, Symbol) and e.symbol_kind == "PARAMETER" and e.name == "em"
    )
    assignments = (
        ConnectionAssignment(
            symbol_key=symbol.logical_key,
            context=ConnectionContext(
                connection_key="persistence-unit",
                database_key="orders",
                version_key="v1",
                search_path=("public",),
            ),
        ),
    )
    return repo, assignments


def test_orm_roundtrip_native_separation_db_policy_and_incremental_reuse(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, assignments = await setup(conn, tmp_path)
            first = await index_java_orm(conn, repo, tmp_path, assignments)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            assert len([e for e in batch.entities if isinstance(e, SqlExecute)]) == 1
            assert len([e for e in batch.entities if isinstance(e, OrmOperation)]) == 3
            assert any(
                isinstance(e, OrmMapping)
                and e.column_name
                and e.column_name.text == "id"
                for e in batch.entities
            )
            targets = [
                e
                for e in batch.entities
                if isinstance(e, Relation)
                and e.relation_kind == RelationKind.ORM_DATABASE_TARGET
            ]
            assert targets and all(e.resolution.status == "UNRESOLVED" for e in targets)
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ucm_orm_mapping_names WHERE snapshot_id=$1",
                    first.snapshot_id,
                )
            unchanged = await index_java_orm(conn, repo, tmp_path, assignments)
            assert unchanged.plan.reanalyze == () and unchanged.plan.reused == (
                "Dao.java",
                "User.java",
            )
            await validate_snapshot(conn, unchanged.snapshot_id)
            restored = await load_snapshot_batch(conn, unchanged.snapshot_id)
            assert {e.id: e for e in batch.entities} == {
                e.id: e for e in restored.entities
            }
            identity = await index_java_orm(
                conn, repo, tmp_path, assignments, naming_policy="IDENTITY"
            )
            assert identity.plan.reanalyze == ("Dao.java", "User.java")
            await validate_snapshot(conn, identity.snapshot_id)
            resolved = await load_snapshot_batch(conn, identity.snapshot_id)
            assert any(
                isinstance(e, Relation)
                and e.relation_kind == RelationKind.ORM_DATABASE_TARGET
                and e.resolution.status == "RESOLVED"
                for e in resolved.entities
            )
            (tmp_path / "User.java").write_text(
                (tmp_path / "User.java")
                .read_text()
                .replace("select u from User u", "select u from User u where u.id=:id")
            )
            changed = await index_java_orm(conn, repo, tmp_path, assignments)
            assert changed.plan.reanalyze == ("Dao.java", "User.java")
            await validate_snapshot(conn, changed.snapshot_id)
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_readiness_rejects_orm_effect_inconsistent_with_api(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, assignments = await setup(conn, tmp_path)
            result = await index_java_orm(conn, repo, tmp_path, assignments)
            await conn.execute(
                "UPDATE ucm_orm_operations SET effect_kind='DELETE' WHERE snapshot_id=$1 AND operation_kind='PERSIST'",
                result.snapshot_id,
            )
            with pytest.raises(ValueError, match="effect must match"):
                await validate_snapshot(conn, result.snapshot_id)
            assert await snapshots.published_snapshot(conn, repo) is None
        finally:
            await conn.close()

    asyncio.run(scenario())
