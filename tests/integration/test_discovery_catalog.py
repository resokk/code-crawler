import asyncio

import asyncpg
import pytest
from test_publication import create, setup

from code_crawler import discovery, publication, snapshots
from code_crawler.jobs import collect_garbage
from code_crawler.publication import (
    publish_snapshot,
    rollback_publication,
    validate_snapshot,
)

pytestmark = pytest.mark.integration


def test_discovery_publication_ambiguity_versions_rollback_and_gc(
    database_url, ucm_batch_factory, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            one = await setup(conn)
            two = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="two", display_name="two", source="fixture"
                ),
            )
            old = await create(conn, one, ucm_batch_factory(one))
            other = await create(conn, two, ucm_batch_factory(two))

            async def lookup(**kwargs):
                return await discovery.lookup(
                    conn,
                    "SYMBOL",
                    ("A.m",),
                    repository_keys=("repo", "two"),
                    allowed_repositories=frozenset(("repo", "two")),
                    **kwargs,
                )

            assert not (await lookup())["items"]
            await validate_snapshot(conn, old)
            assert not (await lookup())["items"]
            await publish_snapshot(conn, one, old, expected_snapshot_id=None)
            await validate_snapshot(conn, other)
            await publish_snapshot(conn, two, other, expected_snapshot_id=None)
            found = await lookup()
            assert len(found["items"]) == 2 and found["resolution"] == "UNRESOLVED"
            assert {r["snapshot_id"] for r in found["items"]} == {old, other}
            assert (await lookup(limit=1))["truncated"]
            with pytest.raises(PermissionError):
                await discovery.lookup(
                    conn,
                    "SYMBOL",
                    ("A.m",),
                    repository_keys=("repo", "two"),
                    allowed_repositories=frozenset(("repo",)),
                )
            signature = await discovery.lookup(
                conn,
                "SYMBOL_SIGNATURE",
                ("A.m", ("A", "String")),
                repository_keys=("repo",),
                allowed_repositories=frozenset(("repo",)),
            )
            assert len(signature["items"]) == 1
            empty = await discovery.lookup(
                conn,
                "SYMBOL_SIGNATURE",
                ("A.m", ()),
                repository_keys=("repo",),
                allowed_repositories=frozenset(("repo",)),
            )
            assert not empty["items"]
            new = await create(conn, one, ucm_batch_factory(one))
            await validate_snapshot(conn, new)
            original = publication.build_generation

            async def fail(*args):
                await original(*args)
                raise RuntimeError("projector failure")

            with monkeypatch.context() as patch:
                patch.setattr(publication, "build_generation", fail)
                with pytest.raises(RuntimeError, match="projector failure"):
                    await publish_snapshot(conn, one, new, expected_snapshot_id=old)
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM search_discovery_generations WHERE snapshot_id=$1)",
                new,
            )
            assert {r["snapshot_id"] for r in (await lookup())["items"]} == {old, other}
            await publish_snapshot(conn, one, new, expected_snapshot_id=old)
            assert {r["snapshot_id"] for r in (await lookup())["items"]} == {new, other}
            assert await discovery.refresh_discovery(
                conn, "repo"
            ) == await conn.fetchval(
                "SELECT generation FROM search_discovery_generations WHERE snapshot_id=$1",
                new,
            )
            await rollback_publication(conn, one, old, expected_snapshot_id=new)
            assert {r["snapshot_id"] for r in (await lookup())["items"]} == {old, other}
            await collect_garbage(conn, keep_retired=0)
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM search_discovery_entries WHERE snapshot_id=$1)",
                new,
            )
            assert len((await lookup())["items"]) == 2
        finally:
            await conn.close()

    asyncio.run(run())


def test_bpmn_process_projection_uses_explicit_id(database_url, tmp_path):
    from code_crawler import db, repos
    from code_crawler.bpmn_adapter import BpmnSourceAdapter
    from code_crawler.source_adapters import AdapterRegistry, index_sources

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "Catalog Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            (tmp_path / "process.bpmn").write_text(
                '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"><process id="p" name="Display"/></definitions>'
            )
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="bpmn", display_name="bpmn", source=str(tmp_path)
                ),
            )
            result = await index_sources(
                conn, repo, tmp_path, AdapterRegistry((BpmnSourceAdapter(),))
            )
            await validate_snapshot(conn, result.snapshot_id)
            await publish_snapshot(
                conn, repo, result.snapshot_id, expected_snapshot_id=None
            )
            found = await discovery.lookup(
                conn,
                "BPMN_PROCESS",
                ("p",),
                repository_keys=("bpmn",),
                allowed_repositories=frozenset(("bpmn",)),
            )
            assert len(found["items"]) == 1
            assert found["items"][0]["source_file_id"]
            assert not (
                await discovery.lookup(
                    conn,
                    "BPMN_PROCESS",
                    ("Display",),
                    repository_keys=("bpmn",),
                    allowed_repositories=frozenset(("bpmn",)),
                )
            )["items"]
        finally:
            await conn.close()

    asyncio.run(run())
