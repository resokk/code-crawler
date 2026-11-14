import asyncio
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.java_lineage import index_java_lineage
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import Relation, RelationKind, SqlBinding, SqlPlaceholder

pytestmark = pytest.mark.integration


async def setup(conn: asyncpg.Connection, root: Path) -> UUID:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Lineage Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    (
        root / "A.java"
    ).write_text("""import java.sql.Connection;import java.sql.PreparedStatement;
      import java.util.Map;import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
      class A {void m(Connection c,int id,String name,NamedParameterJdbcTemplate j){
      PreparedStatement p=c.prepareStatement("update users set name=? where id=?");
      p.setString(1,name);p.setInt(2,id);p.executeUpdate();p.clearParameters();p.executeUpdate();
      j.update("delete from users where id=:id",Map.of("id",id));}}""")
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="lineage", display_name="lineage", source=str(root)
        ),
    )


def test_lineage_roundtrip_publication_immutability_and_reuse(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            first = await index_java_lineage(conn, repo, tmp_path)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            assert {"BOUND", "MISSING"} <= {
                e.status for e in batch.entities if isinstance(e, SqlBinding)
            }
            assert {
                e.parameter_kind
                for e in batch.entities
                if isinstance(e, SqlPlaceholder)
            } == {"POSITIONAL", "NAMED"}
            for kind in (
                RelationKind.VALUE_OF,
                RelationKind.VALUE_BINDS_SQL,
                RelationKind.BINDS_PARAMETER,
                RelationKind.PARAMETER_COLUMN,
            ):
                assert any(
                    isinstance(e, Relation)
                    and e.relation_kind == kind
                    and e.resolution.status == "RESOLVED"
                    for e in batch.entities
                )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ucm_sql_binding_reasons WHERE snapshot_id=$1",
                    first.snapshot_id,
                )
            unchanged = await index_java_lineage(conn, repo, tmp_path)
            assert unchanged.plan.reanalyze == () and unchanged.plan.reused == (
                "A.java",
            )
            await validate_snapshot(conn, unchanged.snapshot_id)
            restored = await load_snapshot_batch(conn, unchanged.snapshot_id)
            assert {e.id: e for e in batch.entities} == {
                e.id: e for e in restored.entities
            }
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_readiness_rejects_binding_api_inconsistent_with_setter(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            result = await index_java_lineage(conn, repo, tmp_path)
            await conn.execute(
                "UPDATE ucm_sql_bindings SET api='wrong.setter' WHERE snapshot_id=$1 AND setter_operation_id IS NOT NULL",
                result.snapshot_id,
            )
            with pytest.raises(ValueError, match="setter must match"):
                await validate_snapshot(conn, result.snapshot_id)
            assert await snapshots.published_snapshot(conn, repo) is None
        finally:
            await conn.close()

    asyncio.run(scenario())
