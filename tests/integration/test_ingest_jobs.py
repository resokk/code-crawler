import asyncio
import json
from pathlib import Path

import asyncpg
import pytest
from test_publication_cli import command

from code_crawler import db, jobs, repos

pytestmark = pytest.mark.integration


async def commit(root: Path, text: str) -> None:
    (root / "A.java").write_text(text)
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)


async def index(database_url: str, root: Path, *extra: str) -> tuple[int, str]:
    return await command(
        database_url, "index-sources", str(root), "--repository-key", "repo", *extra
    )


async def prepare(conn: asyncpg.Connection, root: Path) -> None:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Jobs Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)


def test_failed_job_keeps_diagnostics_and_retries_safely(
    database_url: str, tmp_path: Path
) -> None:
    async def run() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await prepare(conn, tmp_path)
            await commit(tmp_path, "class A{void m( {")
            code, _ = await index(database_url, tmp_path, "--publish")
            assert code == 1
            job = await conn.fetchrow("SELECT * FROM ingest_jobs")
            failure = json.loads(job["failure"])
            assert (job["state"], job["stage"], job["attempt"]) == (
                "FAILED",
                "INDEX",
                1,
            )
            assert failure["type"] == "AdapterError" and failure["issues"]
            assert failure["issues"][0]["path"] == "A.java"
            assert await conn.fetchval("SELECT count(*) FROM ucm_snapshots") == 0

            assert await conn.fetchval(jobs._LOCK, jobs._JOB_LOCK, str(job["id"]))
            code, output = await command(database_url, "jobs", "retry", str(job["id"]))
            assert code == 1 and "another process" in output
            await conn.fetchval(jobs._UNLOCK, jobs._JOB_LOCK, str(job["id"]))

            await commit(tmp_path, "class A{}")
            code, output = await command(database_url, "jobs", "retry", str(job["id"]))
            assert code == 0, output
            job = await conn.fetchrow("SELECT * FROM ingest_jobs")
            assert (job["state"], job["stage"], job["attempt"]) == (
                "SUCCEEDED",
                "PUBLISH",
                2,
            )
            assert job["failure"] is None
            assert (
                await conn.fetchval(
                    "SELECT state FROM ucm_snapshots WHERE id=$1", job["snapshot_id"]
                )
                == "PUBLISHED"
            )
            code, output = await command(database_url, "jobs", "retry", str(job["id"]))
            assert code == 1 and "already succeeded" in output
            code, output = await command(database_url, "jobs", "list")
            assert code == 0 and "SUCCEEDED" in output
        finally:
            await conn.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("foreign_table", "snapshot_type"),
    [("application_snapshots", "uuid"), ("ucm_application_snapshots", "text")],
)
def test_gc_removes_abandoned_building_and_old_retired_only(
    database_url: str, tmp_path: Path, foreign_table: str, snapshot_type: str
) -> None:
    async def run() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await prepare(conn, tmp_path)
            published = []
            for text in ("class A{}", "class A{int a;}", "class A{int b;}"):
                await commit(tmp_path, text)
                code, output = await index(database_url, tmp_path, "--publish")
                assert code == 0, output
                published.append(
                    await conn.fetchval(
                        "SELECT snapshot_id FROM ucm_repository_publications"
                    )
                )
            await commit(tmp_path, "class A{int c;}")
            code, output = await index(database_url, tmp_path)
            assert code == 0, output
            building = await conn.fetchval(
                "SELECT id FROM ucm_snapshots WHERE state='BUILDING'"
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ucm_entities WHERE snapshot_id=$1", published[0]
                )

            await conn.execute(
                f"CREATE TABLE public.{foreign_table} (snapshot_id {snapshot_type} PRIMARY KEY, payload text NOT NULL)"
            )
            protected = [
                (str(snap) if snapshot_type == "text" else snap, f"payload:{i}")
                for i, snap in enumerate([building, *published])
            ]
            await conn.executemany(
                f"INSERT INTO public.{foreign_table} VALUES ($1,$2)", protected
            )

            repository = await conn.fetchval("SELECT id FROM ucm_repositories")
            # A RUNNING row without its session lock is a job whose process died.
            await conn.execute(
                "INSERT INTO ingest_jobs(id,repository_id,parameters) VALUES ($1,$2,'{}')",
                building,
                repository,
            )
            code, output = await command(
                database_url,
                "snapshot",
                "gc",
                "--building-older-than",
                "0",
                "--keep-retired",
                "1",
            )
            assert code == 0, output
            assert {
                tuple(row)
                for row in await conn.fetch(f"SELECT * FROM public.{foreign_table}")
            } == set(protected)
            assert (
                await conn.fetchval(
                    "SELECT state FROM ingest_jobs WHERE id=$1", building
                )
                == "FAILED"
            )
            assert {
                r["id"]: r["state"]
                for r in await conn.fetch("SELECT id,state FROM ucm_snapshots")
            } == {published[1]: "RETIRED", published[2]: "PUBLISHED"}
            assert (
                await conn.fetchval(
                    "SELECT count(DISTINCT snapshot_id) FROM ucm_entities"
                )
                == 2
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ingest_jobs WHERE snapshot_id IS NULL"
                )
                == 3
            )  # jobs outlive their collected snapshots
            code, output = await index(database_url, tmp_path, "--publish")
            assert code == 0, output
            code, _ = await command(database_url, "snapshot", "gc")
            assert code != 0
        finally:
            await conn.close()

    asyncio.run(run())


def test_gc_registry_covers_migrated_snapshot_tables(
    database_url: str, tmp_path: Path
) -> None:
    async def run() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await prepare(conn, tmp_path)
            tables = {
                row["table_name"]
                for row in await conn.fetch(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND column_name='snapshot_id'"
                )
            }
            assert len(jobs._SNAPSHOT_TABLES) == len(set(jobs._SNAPSHOT_TABLES))
            assert set(jobs._SNAPSHOT_TABLES) == tables - {
                "ingest_jobs",
                "ucm_repository_publications",
            }
        finally:
            await conn.close()

    asyncio.run(run())
