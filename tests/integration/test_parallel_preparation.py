import asyncio
import multiprocessing as mp

import asyncpg
import pytest

from code_crawler import db, incremental, repos, snapshots
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.java_parallel import JavaProcessPool
from code_crawler.kafka_adapter import KafkaSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.source_adapters import AdapterError, AdapterRegistry, index_sources

pytestmark = pytest.mark.integration


def test_process_facts_reuse_shutdown_before_write_and_failure_publication(
    database_url, tmp_path, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            for migration in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, migration)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            (tmp_path / "A.java").write_text(
                'class A {void m(){use("select id from t");}}'
            )
            (tmp_path / "B.java").write_text("class B {void m(){new A().m();}}")
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="repo", display_name="repo", source=str(tmp_path)
                ),
            )

            def registry(workers):
                return AdapterRegistry(
                    (
                        KafkaSourceAdapter(
                            java_adapter=JavaSourceAdapter(
                                profile="sql", analysis_workers=workers
                            )
                        ),
                    )
                )

            stage = incremental._stage

            async def assert_parent_only(*args, **kwargs):
                assert not mp.active_children(), (
                    "children still live during canonical write"
                )
                return await stage(*args, **kwargs)

            monkeypatch.setattr(incremental, "_stage", assert_parent_only)
            first = await index_sources(conn, repo, tmp_path, registry(2))
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            original = await load_snapshot_batch(conn, first.snapshot_id)
            # Worker count is operational only: unchanged facts are reused without a pool.
            created = JavaProcessPool.__init__

            def unexpected(*args, **kwargs):
                pytest.fail("reused files started worker processes")

            monkeypatch.setattr(JavaProcessPool, "__init__", unexpected)
            second = await index_sources(conn, repo, tmp_path, registry(4))
            assert len(second.plan.reused) == 2 and not second.plan.reanalyze
            await validate_snapshot(conn, second.snapshot_id)
            assert await load_snapshot_batch(conn, second.snapshot_id) == original
            monkeypatch.setattr(JavaProcessPool, "__init__", created)
            (tmp_path / "A.java").write_text(
                'class A {void m(){use("select name from t");}}'
            )
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "change", cwd=tmp_path)

            async def fail(*args, **kwargs):
                raise RuntimeError("worker injected failure")

            monkeypatch.setattr(JavaProcessPool, "analyze", fail)
            before = await conn.fetchval("SELECT count(*) FROM ucm_snapshots")
            with pytest.raises(AdapterError, match="worker injected failure"):
                await index_sources(conn, repo, tmp_path, registry(2))
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
            assert await conn.fetchval("SELECT count(*) FROM ucm_snapshots") == before
            assert not mp.active_children()
        finally:
            await conn.close()

    asyncio.run(run())
