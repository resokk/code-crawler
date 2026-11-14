import asyncio
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.java_sql import index_java_sql
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import Relation, SqlConstruction

pytestmark = pytest.mark.integration


def test_sql_variants_fragments_and_no_execution_survive_storage(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git(
                "config", "user.name", "SQL Construction Test", cwd=tmp_path
            )
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            (tmp_path / "A.java").write_text("""class A { void m(boolean f,String p){
                String unused="delete from archive";
                String q=f?"select id from a":"select id from b"; use(q);
                use("select id from t where name="+p);
            } }""")
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="java", display_name="java", source=str(tmp_path)
                ),
            )
            first = await index_java_sql(conn, repo, tmp_path)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            constructions = [
                e for e in batch.entities if isinstance(e, SqlConstruction)
            ]
            assert any(
                {v.text for v in e.variants} == {"select id from a", "select id from b"}
                for e in constructions
            )
            assert any(
                v.text == "delete from archive"
                for e in constructions
                for v in e.variants
            )
            assert any(
                f.kind == "DYNAMIC" and f.source_range is not None
                for e in constructions
                for v in e.variants
                for f in v.fragments
            )
            assert not any(
                e.relation_kind.value.startswith("EXECUTES")
                for e in batch.entities
                if isinstance(e, Relation)
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_sql_fragments WHERE snapshot_id=$1 AND kind='DYNAMIC'",
                    first.snapshot_id,
                )
                > 0
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ucm_sql_fragments WHERE snapshot_id=$1",
                    first.snapshot_id,
                )
            unchanged = await index_java_sql(conn, repo, tmp_path)
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


def test_corrupt_fragment_text_is_rejected_by_readiness_gate(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "SQL Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            (tmp_path / "A.java").write_text(
                'class A { void m(){ String q="delete from t"; } }'
            )
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="java", display_name="java", source=str(tmp_path)
                ),
            )
            result = await index_java_sql(conn, repo, tmp_path)
            await conn.execute(
                "UPDATE ucm_sql_fragments SET text='corrupted' WHERE snapshot_id=$1",
                result.snapshot_id,
            )
            with pytest.raises(ValueError, match="fragments"):
                await validate_snapshot(conn, result.snapshot_id)
            assert await snapshots.published_snapshot(conn, repo) is None
        finally:
            await conn.close()

    asyncio.run(scenario())
