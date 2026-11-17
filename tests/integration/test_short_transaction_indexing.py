import asyncio
import json
import os
import stat
import sys
from contextlib import asynccontextmanager

import asyncpg
import pytest
from test_incremental_indexing import Analyzer, build, publish, setup

from code_crawler import incremental, snapshots
from code_crawler.jobs import collect_garbage
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import Symbol

pytestmark = pytest.mark.integration


def test_slow_analysis_has_no_transaction_and_private_spool(
    database_url, tmp_path, monkeypatch
):
    streams = []
    original = incremental._analysis_spool

    @asynccontextmanager
    async def observe():
        async with original() as stream:
            streams.append(stream)
            assert stat.S_IMODE(os.fstat(stream.fileno()).st_mode) == 0o600
            assert os.fstat(stream.fileno()).st_nlink == 0
            yield stream

    monkeypatch.setattr(incremental, "_analysis_spool", observe)

    async def run():
        conn = await asyncpg.connect(database_url)
        observer = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path, {"A.java": "A", "B.java": "B"})
            await conn.execute("SET idle_in_transaction_session_timeout='100ms'")
            parser = Analyzer({"A.java", "B.java"})

            async def slow(sources):
                assert not conn.is_in_transaction()
                row = await observer.fetchrow(
                    "SELECT state,xact_start,backend_xmin FROM pg_stat_activity WHERE pid=$1",
                    conn.get_server_pid(),
                )
                assert (
                    row["state"] == "idle"
                    and row["xact_start"] is None
                    and row["backend_xmin"] is None
                )
                assert streams[0].tell() > 0
                await asyncio.sleep(0.2)
                return await parser(sources)

            result = await build(conn, repo, tmp_path, slow)
            assert (
                result.preparation_seconds >= 0.2
                and result.write_transaction_seconds > 0
                and result.spool_bytes > 0
            )
            assert streams[0].closed
            await publish(conn, repo, result)
            before = await load_snapshot_batch(conn, result.snapshot_id)
            again = await build(conn, repo, tmp_path, parser)
            await validate_snapshot(conn, again.snapshot_id)
            assert await load_snapshot_batch(conn, again.snapshot_id) == before
        finally:
            await conn.close()
            await observer.close()

    asyncio.run(run())


def test_concurrent_publication_and_gc_keep_exact_baseline(database_url, tmp_path):
    async def run():
        conn = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        try:
            root = tmp_path / "one"
            root.mkdir()
            repo = await setup(conn, root, {"A.java": "A", "B.java": "B"})
            parser = Analyzer({"A.java", "B.java"})
            baseline = await build(conn, repo, root, parser)
            await publish(conn, repo, baseline)
            competitor_root = tmp_path / "two"
            competitor_root.mkdir()
            await setup(other, competitor_root, {"A.java": "A", "B.java": "NewB"})
            competitor = await build(other, repo, competitor_root, parser)
            await validate_snapshot(other, competitor.snapshot_id)
            (root / "A.java").write_text("NewA")

            async def race(sources):
                assert not conn.is_in_transaction()
                async with other.transaction():
                    await other.execute(
                        "SELECT id FROM ucm_repositories WHERE id=$1 FOR UPDATE NOWAIT",
                        repo,
                    )
                await asyncio.wait_for(
                    publish_snapshot(
                        other,
                        repo,
                        competitor.snapshot_id,
                        expected_snapshot_id=baseline.snapshot_id,
                    ),
                    3,
                )
                report = await collect_garbage(other, keep_retired=0)
                assert baseline.snapshot_id in report["skipped"]
                assert baseline.snapshot_id not in report["retired"]
                return await parser(sources)

            result = await build(conn, repo, root, race)
            assert (
                result.base_snapshot_id == baseline.snapshot_id
                and result.plan.reused == ("B.java",)
            )
            await validate_snapshot(conn, result.snapshot_id)
            facts = await load_snapshot_batch(conn, result.snapshot_id)
            assert {e.name for e in facts.entities if isinstance(e, Symbol)} == {
                "NewA",
                "B",
            }
            with pytest.raises(ValueError, match="pointer changed"):
                await publish_snapshot(
                    conn,
                    repo,
                    result.snapshot_id,
                    expected_snapshot_id=result.base_snapshot_id,
                )
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == competitor.snapshot_id
            assert (
                baseline.snapshot_id
                in (await collect_garbage(other, keep_retired=0))["retired"]
            )
        finally:
            await conn.close()
            await other.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure",
    [
        "analysis",
        "spool",
        "stage",
        "transfer",
        "archive_change",
        "final_check_change",
        "cancel_analysis",
        "cancel_stage",
    ],
)
def test_failures_leave_no_snapshot_or_spool(
    database_url, tmp_path, monkeypatch, failure
):
    streams = []
    original = incremental._analysis_spool

    @asynccontextmanager
    async def observe():
        async with original() as stream:
            streams.append(stream)
            yield stream

    monkeypatch.setattr(incremental, "_analysis_spool", observe)

    async def run():
        conn = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path, {"A.java": "A"})
            parser = Analyzer({"A.java"})
            first = await build(conn, repo, tmp_path, parser)
            await publish(conn, repo, first)
            before = await conn.fetchval("SELECT count(*) FROM ucm_snapshots")
            old = await load_snapshot_batch(conn, first.snapshot_id)
            (tmp_path / "A.java").write_text("ChangedA")

            async def analysis(sources):
                if failure == "analysis":
                    raise RuntimeError("injected analysis failure")
                if failure == "cancel_analysis":
                    raise asyncio.CancelledError
                return await parser(sources)

            if failure == "spool":

                def broken(*args):
                    raise OSError("injected spool failure")

                monkeypatch.setattr(incremental, "_spool_facts", broken)
            if failure in ("stage", "transfer", "cancel_stage"):

                async def broken(*args):
                    if failure == "cancel_stage":
                        raise asyncio.CancelledError
                    raise RuntimeError("injected write failure")

                monkeypatch.setattr(
                    incremental,
                    "_transfer" if failure == "transfer" else "_stage",
                    broken,
                )
            if failure in ("archive_change", "final_check_change"):
                name = "archive_sources" if failure == "archive_change" else "_check"
                delegate = getattr(incremental, name)

                async def mutate(*args, **kwargs):
                    result = await delegate(*args, **kwargs)
                    (tmp_path / "A.java").write_text("MutatedAgain")
                    return result

                monkeypatch.setattr(incremental, name, mutate)
            with pytest.raises(
                (RuntimeError, ValueError, OSError, asyncio.CancelledError)
            ):
                await build(conn, repo, tmp_path, analysis)
            assert all(stream.closed for stream in streams)
            assert not conn.is_in_transaction()
            assert before == await conn.fetchval("SELECT count(*) FROM ucm_snapshots")
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
            assert await load_snapshot_batch(conn, first.snapshot_id) == old
            assert (
                await conn.fetchval("SELECT to_regclass('pg_temp.ingest_refs')") is None
            )
            assert await other.fetchval(
                "SELECT pg_try_advisory_lock($1,hashtext($2::text))",
                snapshots._SNAPSHOT_LOCK,
                str(first.snapshot_id),
            )
        finally:
            await conn.close()
            await other.close()

    asyncio.run(run())


def test_process_kill_removes_spool_and_lease(database_url, tmp_path):
    async def run():
        conn = await asyncpg.connect(database_url)
        child = None
        try:
            root = tmp_path / "repo"
            root.mkdir()
            repo = await setup(conn, root, {f"A{i}.java": "A" for i in range(65)})
            first = await build(
                conn, repo, root, Analyzer({f"A{i}.java" for i in range(65)})
            )
            await publish(conn, repo, first)
            spool_dir = tmp_path / "spool"
            spool_dir.mkdir()
            code = """import asyncio,json,sys
from pathlib import Path
from uuid import UUID
import asyncpg
from code_crawler.incremental import index_incremental,FileAnalysis
async def main():
 c=await asyncpg.connect(sys.argv[1])
 calls=0
 async def analyze(sources):
  nonlocal calls
  calls+=1
  if calls==2:
   print(json.dumps({"pid":c.get_server_pid(),"in_transaction":c.is_in_transaction()}),flush=True)
   await asyncio.Event().wait()
  return tuple(FileAnalysis(path=s.file.path) for s in sources)
 await index_incremental(c,UUID(sys.argv[2]),Path(sys.argv[3]),analyze,languages={".java":"java"},analysis_version="crash-profile")
asyncio.run(main())
"""
            child = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                code,
                database_url,
                str(repo),
                str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "TMPDIR": str(spool_dir)},
            )
            ready = json.loads(await asyncio.wait_for(child.stdout.readline(), 20))
            assert not ready["in_transaction"]
            assert list(spool_dir.iterdir()) == []
            assert not await conn.fetchval(
                "SELECT pg_try_advisory_lock($1,hashtext($2::text))",
                snapshots._SNAPSHOT_LOCK,
                str(first.snapshot_id),
            )
            child.kill()
            await child.wait()

            async def released():
                while not await conn.fetchval(
                    "SELECT pg_try_advisory_lock($1,hashtext($2::text))",
                    snapshots._SNAPSHOT_LOCK,
                    str(first.snapshot_id),
                ):
                    await asyncio.sleep(0.02)

            await asyncio.wait_for(released(), 5)
            assert list(spool_dir.iterdir()) == []
            assert await conn.fetchval("SELECT count(*) FROM ucm_snapshots") == 1
        finally:
            if child is not None and child.returncode is None:
                child.kill()
                await child.wait()
            await conn.close()

    asyncio.run(run())


def test_cancelled_lease_acquisition_preserves_outer_owner(database_url, tmp_path):
    async def run():
        conn = await asyncpg.connect(database_url)
        observer = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path, {"A.java": "A"})
            first = await build(conn, repo, tmp_path, Analyzer({"A.java"}))
            await publish(conn, repo, first)
            acquired, resume = asyncio.Event(), asyncio.Event()

            class Connection:
                def __getattr__(self, name):
                    return getattr(conn, name)

                async def fetchval(self, query, *args):
                    value = await conn.fetchval(query, *args)
                    if "pg_try_advisory_lock_shared" in query:
                        acquired.set()
                        await resume.wait()
                    return value

            async def inner():
                async with snapshots.pinned_baseline(Connection(), repo):
                    pytest.fail("cancelled acquisition entered the body")

            async with snapshots.pinned_baseline(conn, repo):
                task = asyncio.create_task(inner())
                await asyncio.wait_for(acquired.wait(), 3)
                task.cancel()
                resume.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert not await observer.fetchval(
                    "SELECT pg_try_advisory_lock($1,hashtext($2::text))",
                    snapshots._SNAPSHOT_LOCK,
                    str(first.snapshot_id),
                )
            assert await observer.fetchval(
                "SELECT pg_try_advisory_lock($1,hashtext($2::text))",
                snapshots._SNAPSHOT_LOCK,
                str(first.snapshot_id),
            )
            async with conn.transaction():
                with pytest.raises(ValueError, match="free connection"):
                    async with snapshots.pinned_baseline(conn, repo):
                        pass
        finally:
            await conn.close()
            await observer.close()

    asyncio.run(run())


def test_analyzer_observes_a_free_connection(database_url, tmp_path):
    """Behavior-only regression runnable unchanged against the parent implementation."""

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path, {"A.java": "A"})
            parser = Analyzer({"A.java"})

            async def analyze(sources):
                assert not conn.is_in_transaction(), (
                    "CPU analysis ran inside the write transaction"
                )
                return await parser(sources)

            await build(conn, repo, tmp_path, analyze)
        finally:
            await conn.close()

    asyncio.run(run())
