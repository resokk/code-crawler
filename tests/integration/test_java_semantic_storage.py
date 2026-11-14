import asyncio
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.java_semantic import index_java_semantic
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import DataAccess, Relation, RelationKind, SqlStatement

pytestmark = pytest.mark.integration


async def setup(conn: asyncpg.Connection, root: Path) -> UUID:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Semantic Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    (root / "A.java").write_text(
        """import java.sql.Statement; class A {void m(Statement s,String table){
      String unused="delete from archive";
      s.execute("select \\"ID\\" from \\"App\\".\\"Users\\"; update users set value=1");
      s.execute("select id from "+table);
    }}""".replace('\\\\"', '\\"')
    )
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="semantic", display_name="semantic", source=str(root)
        ),
    )


def test_semantic_roundtrip_publication_reuse_and_profile_change(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            first = await index_java_semantic(conn, repo, tmp_path)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            assert any(
                isinstance(e, DataAccess)
                and e.table_name
                and e.table_name.text == "Users"
                and e.table_name.quoted
                for e in batch.entities
            )
            assert any(
                isinstance(e, SqlStatement) and e.parse_status == "PARTIAL"
                for e in batch.entities
            )
            assert any(
                isinstance(e, Relation)
                and e.relation_kind == RelationKind.EXECUTES_STATEMENT
                and e.resolution.status == "RESOLVED"
                for e in batch.entities
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ucm_sql_access_names WHERE snapshot_id=$1",
                    first.snapshot_id,
                )
            unchanged = await index_java_semantic(conn, repo, tmp_path)
            assert unchanged.plan.reanalyze == () and unchanged.plan.reused == (
                "A.java",
            )
            await validate_snapshot(conn, unchanged.snapshot_id)
            restored = await load_snapshot_batch(conn, unchanged.snapshot_id)
            assert {e.id: e for e in batch.entities} == {
                e.id: e for e in restored.entities
            }
            changed = await index_java_semantic(conn, repo, tmp_path, dialect="mysql")
            assert changed.plan.reanalyze == ("A.java",) and changed.plan.reused == ()
            await validate_snapshot(conn, changed.snapshot_id)
            assert all(
                e.dialect == "mysql"
                for e in (await load_snapshot_batch(conn, changed.snapshot_id)).entities
                if isinstance(e, SqlStatement)
            )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_readiness_rejects_access_effect_inconsistent_with_relation(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            result = await index_java_semantic(conn, repo, tmp_path)
            await conn.execute(
                "UPDATE ucm_data_accesses SET access_kind='DELETE' WHERE snapshot_id=$1 AND access_kind='READ'",
                result.snapshot_id,
            )
            with pytest.raises(ValueError, match="statement and effect"):
                await validate_snapshot(conn, result.snapshot_id)
            assert await snapshots.published_snapshot(conn, repo) is None
        finally:
            await conn.close()

    asyncio.run(scenario())
