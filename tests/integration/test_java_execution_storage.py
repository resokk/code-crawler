import asyncio
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.java_execution import index_java_execution
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import Relation, RelationKind, SqlExecute

pytestmark = pytest.mark.integration


async def setup(conn: asyncpg.Connection, root: Path) -> UUID:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Execution Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    (root / "A.java").write_text(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c,PreparedStatement external){String unused="delete from unused_t";PreparedStatement p=c.prepareStatement("select * from t");p.executeQuery();external.execute();}}'
    )
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="execution", display_name="execution", source=str(root)
        ),
    )


def test_execution_roundtrip_publication_reuse_and_immutability(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            first = await index_java_execution(conn, repo, tmp_path)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            assert len([e for e in batch.entities if isinstance(e, SqlExecute)]) == 2
            uses = [
                e
                for e in batch.entities
                if isinstance(e, Relation)
                and e.relation_kind == RelationKind.USES_SQL_CONSTRUCTION
            ]
            assert {e.resolution.status for e in uses} == {"RESOLVED", "UNRESOLVED"}
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ucm_sql_executions WHERE snapshot_id=$1",
                    first.snapshot_id,
                )
            reused = await index_java_execution(conn, repo, tmp_path)
            assert reused.plan.reanalyze == () and reused.plan.reused == ("A.java",)
            await validate_snapshot(conn, reused.snapshot_id)
            restored = await load_snapshot_batch(conn, reused.snapshot_id)
            assert {e.id: e for e in batch.entities} == {
                e.id: e for e in restored.entities
            }
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_readiness_rejects_execution_api_inconsistent_with_call(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            result = await index_java_execution(conn, repo, tmp_path)
            await conn.execute(
                "UPDATE ucm_sql_executions SET api='fake.execute' WHERE snapshot_id=$1",
                result.snapshot_id,
            )
            with pytest.raises(ValueError, match="API must match"):
                await validate_snapshot(conn, result.snapshot_id)
            assert await snapshots.published_snapshot(conn, repo) is None
        finally:
            await conn.close()

    asyncio.run(scenario())
