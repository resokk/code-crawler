import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from code_crawler import cli, db, repos, snapshots
from code_crawler.ingestion import ingest_batch
from code_crawler.publication import publish_snapshot, validate_snapshot

pytestmark = pytest.mark.integration


async def command(database_url, *arguments):
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "from code_crawler.cli import main; main()",
        *arguments,
        env={
            **os.environ,
            "DATABASE_URL": database_url,
            "NO_COLOR": "1",
            "COLUMNS": "160",
        },
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await asyncio.wait_for(process.communicate(), timeout=60)
    return process.returncode, output.decode()


async def initialize(conn):
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="repo", display_name="repo", source="fixture"
        ),
    )


async def create(conn, repo):
    return await snapshots.create_snapshot(
        conn,
        repo,
        snapshots.SnapshotInput(
            commit_hash="commit", source_fingerprint="a" * 64, dirty=False
        ),
    )


def test_manual_validate_publish_idempotence_and_conflict(database_url):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await initialize(conn)
            old = await create(conn, repo)
            code, output = await command(database_url, "snapshot", "validate", str(old))
            assert (
                code == 0
                and "READY" in output
                and "entity_count" in output
                and "diagnostics" in output
            )
            assert await snapshots.published_snapshot(conn, repo) is None
            code, output = await command(
                database_url,
                "snapshot",
                "publish",
                str(old),
                "--expected-current",
                "none",
            )
            assert code == 0 and "PUBLISHED" in output
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            code, _ = await command(
                database_url,
                "snapshot",
                "publish",
                str(old),
                "--expected-current",
                str(old),
            )
            assert code == 0
            target = await create(conn, repo)
            concurrent = await create(conn, repo)
            code, _ = await command(
                database_url,
                "snapshot",
                "publish",
                str(concurrent),
                "--expected-current",
                str(old),
            )
            assert code == 0
            code, output = await command(
                database_url,
                "snapshot",
                "publish",
                str(target),
                "--expected-current",
                str(old),
            )
            assert code == 1 and "publication pointer changed" in output
            assert (await snapshots.published_snapshot(conn, repo))["id"] == concurrent
            assert (
                await conn.fetchval(
                    "SELECT state FROM ucm_snapshots WHERE id=$1", target
                )
                == "READY"
            )
            code, _ = await command(
                database_url,
                "snapshot",
                "publish",
                str(uuid4()),
                "--expected-current",
                str(concurrent),
            )
            assert code == 1
            assert (await snapshots.published_snapshot(conn, repo))["id"] == concurrent
        finally:
            await conn.close()

    asyncio.run(run())


def test_invalid_snapshot_cannot_replace_publication(database_url, ucm_batch_factory):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await initialize(conn)
            old = await create(conn, repo)
            await validate_snapshot(conn, old)
            await publish_snapshot(conn, repo, old, expected_snapshot_id=None)
            invalid = await create(conn, repo)
            await ingest_batch(conn, invalid, ucm_batch_factory(repo))
            await conn.execute(
                "UPDATE ucm_entities SET logical_key='changed' WHERE snapshot_id=$1 AND entity_type='VALUE' AND logical_key='text'",
                invalid,
            )
            for action in ("validate", "publish"):
                arguments = ["snapshot", action, str(invalid)]
                if action == "publish":
                    arguments += ["--expected-current", str(old)]
                code, _ = await command(database_url, *arguments)
                assert code == 1
                assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_snapshot_validations WHERE snapshot_id=$1)",
                invalid,
            )
        finally:
            await conn.close()

    asyncio.run(run())


async def prepare_git(root: Path):
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Publication CLI Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    (root / "A.java").write_text("class A { void target() {} void run(){ target(); } }")
    (root / "Broken.groovy").write_text("class {")
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)


def test_index_sources_optional_publication_and_repeated_index(database_url, tmp_path):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await initialize(conn)
            await prepare_git(tmp_path)
            arguments = [
                "index-sources",
                str(tmp_path),
                "--repository-key",
                "repo",
                "--java-profile",
                "calls",
            ]
            code, output = await command(database_url, *arguments)
            assert code == 0 and "BUILDING" in output
            repo = await conn.fetchval(
                "SELECT id FROM ucm_repositories WHERE repository_key='repo'"
            )
            assert await snapshots.published_snapshot(conn, repo) is None
            code, output = await command(database_url, *arguments, "--publish")
            assert code == 0 and "PUBLISHED" in output and "ERROR" in output
            first = (await snapshots.published_snapshot(conn, repo))["id"]
            ids = await conn.fetch(
                "SELECT entity_id FROM ucm_entities WHERE snapshot_id=$1 ORDER BY entity_id",
                first,
            )
            code, _ = await command(database_url, *arguments, "--publish")
            assert code == 0
            second = (await snapshots.published_snapshot(conn, repo))["id"]
            assert second != first
            assert ids == await conn.fetch(
                "SELECT entity_id FROM ucm_entities WHERE snapshot_id=$1 ORDER BY entity_id",
                second,
            )
            assert (
                await conn.fetchval(
                    "SELECT state FROM ucm_snapshots WHERE id=$1", first
                )
                == "RETIRED"
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_auto_publication_uses_original_base_pointer(
    database_url, tmp_path, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await initialize(conn)
            old = await create(conn, repo)
            await validate_snapshot(conn, old)
            await publish_snapshot(conn, repo, old, expected_snapshot_id=None)
            await prepare_git(tmp_path)
            original = cli.index_sources
            targets = []

            async def race(connection, repository, root, registry):
                result = await original(connection, repository, root, registry)
                concurrent = await create(connection, repository)
                await validate_snapshot(connection, concurrent)
                await publish_snapshot(
                    connection, repository, concurrent, expected_snapshot_id=old
                )
                targets.extend([result.snapshot_id, concurrent])
                return result

            monkeypatch.setattr(cli, "index_sources", race)
            monkeypatch.setenv("DATABASE_URL", database_url)
            with pytest.raises(SystemExit) as error:
                await cli.index_registered(
                    str(tmp_path), "repo", "calls", "postgres", "UNKNOWN", publish=True
                )
            assert error.value.code == 1
            assert (await snapshots.published_snapshot(conn, repo))["id"] == targets[1]
            assert (
                await conn.fetchval(
                    "SELECT state FROM ucm_snapshots WHERE id=$1", targets[0]
                )
                == "READY"
            )
        finally:
            await conn.close()

    asyncio.run(run())
