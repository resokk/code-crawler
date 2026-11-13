import asyncio
from uuid import UUID, uuid4

import asyncpg
import pytest

from code_crawler import db, snapshots
from code_crawler.publication import publish_snapshot, validate_snapshot

pytestmark = pytest.mark.integration


async def initialize(conn: asyncpg.Connection) -> None:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")


def metadata(dirty: bool = False) -> snapshots.SnapshotInput:
    return snapshots.SnapshotInput(
        commit_hash="abc123", branch=None, source_fingerprint="a" * 64, dirty=dirty
    )


async def register(conn: asyncpg.Connection, key: str = "org/app") -> UUID:
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(repository_key=key, display_name="app", source=key),
    )


def test_repository_identity_and_multiple_snapshots(database_url: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await initialize(conn)
            first = await register(conn)
            assert await register(conn) == first
            other = await register(conn, "other/app")
            assert other != first
            a = await snapshots.create_snapshot(conn, first, metadata())
            b = await snapshots.create_snapshot(conn, first, metadata(True))
            assert a != b
            assert await snapshots.published_snapshot(conn, first) is None
            rows = await conn.fetch("SELECT * FROM public.ucm_snapshots ORDER BY dirty")
            assert [row["state"] for row in rows] == ["BUILDING", "BUILDING"]
            assert [row["dirty"] for row in rows] == [False, True]
            assert all(
                row["branch"] is None and row["commit_hash"] == "abc123" for row in rows
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM public.ucm_repositories WHERE display_name='app'"
                )
                == 2
            )
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await snapshots.create_snapshot(conn, uuid4(), metadata())
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_snapshot_lifecycle_metadata_and_pointer_ownership(database_url: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await initialize(conn)
            repo = await register(conn)
            other = await register(conn, "other/app")
            old = await snapshots.create_snapshot(conn, repo, metadata())
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "UPDATE public.ucm_snapshots SET state='READY' WHERE id=$1", old
                )
            await validate_snapshot(conn, old)
            await publish_snapshot(conn, repo, old, expected_snapshot_id=None)
            new = await snapshots.create_snapshot(conn, repo, metadata(True))
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            for assignment in (
                "commit_hash='changed'",
                "dirty=true",
                "source_fingerprint='b'",
                "branch='main'",
            ):
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(
                        f"UPDATE public.ucm_snapshots SET {assignment} WHERE id=$1", old
                    )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "UPDATE public.ucm_snapshots SET state='BUILDING' WHERE id=$1", old
                )
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute(
                    "INSERT INTO public.ucm_repository_publications(repository_id,snapshot_id) VALUES ($1,$2)",
                    other,
                    old,
                )
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute("DELETE FROM public.ucm_snapshots WHERE id=$1", old)
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            assert (
                await conn.fetchval(
                    "SELECT state FROM public.ucm_snapshots WHERE id=$1", new
                )
                == "BUILDING"
            )
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM ucm_repository_publications WHERE repository_id=$1",
                    repo,
                )
                await conn.execute(
                    "UPDATE public.ucm_snapshots SET state='RETIRED' WHERE id=$1", old
                )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "UPDATE public.ucm_snapshots SET state='PUBLISHED' WHERE id=$1", old
                )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_upgrade_preserves_legacy_data(database_url: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            names = await db.begin_migration(conn, init=True)
            for name in names[:2]:
                await db.apply_migration(conn, name)
            repo = await conn.fetchval(
                "INSERT INTO repos(name,source,path) VALUES ('legacy','fixture','/fixture') RETURNING id"
            )
            node = await conn.fetchval(
                "INSERT INTO nodes(repo_id,kind,name,qualified_name) VALUES ($1,'class','A','A') RETURNING id",
                repo,
            )
            await initialize(conn)
            assert (
                await conn.fetchval("SELECT name FROM nodes WHERE id=$1", node) == "A"
            )
            assert (
                await conn.fetchval("SELECT name FROM repos WHERE id=$1", repo)
                == "legacy"
            )
            assert await db.schema_state(conn) == ([], [])
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_concurrent_registration_returns_same_uuid(database_url: str) -> None:
    async def scenario() -> None:
        first = await asyncpg.connect(database_url)
        second = await asyncpg.connect(database_url)
        try:
            await initialize(first)
            ids = await asyncio.wait_for(
                asyncio.gather(register(first), register(second)), timeout=10
            )
            assert ids[0] == ids[1]
            assert (
                await first.fetchval("SELECT count(*) FROM public.ucm_repositories")
                == 1
            )
        finally:
            await first.close()
            await second.close()

    asyncio.run(scenario())
