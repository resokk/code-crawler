import asyncio
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
from test_publication import create, setup

from code_crawler import jobs, snapshots
from code_crawler.ingestion import UcmBatch
from code_crawler.publication import publish_snapshot, validate_snapshot
from code_crawler.search_storage import read_search_documents, rebuild_search_documents

pytestmark = pytest.mark.integration


def test_search_generations(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            snapshot = await create(conn, repo, ucm_batch_factory(repo))
            with pytest.raises(ValueError, match="validated"):
                await rebuild(conn, repo, snapshot)
            await validate_snapshot(conn, snapshot)
            await publish_snapshot(conn, repo, snapshot, expected_snapshot_id=None)
            with pytest.raises(LookupError):
                await read(conn, repo)
            first = await rebuild(conn, repo, snapshot)
            before = await read(conn, repo)
            assert before and {d["generation_id"] for d in before} == {first}
            assert all(d["snapshot_id"] == snapshot for d in before)
            assert all(d["provenance"]["entity_id"] == d["entity_id"] for d in before)
            relations = [r for d in before for r in d["provenance"]["relations"]]
            assert any(
                r["resolution"]["status"] == "PARTIAL" and r["certainty"] == "INFERRED"
                for r in relations
            )
            assert any(
                r["coverage"]["status"] == "PARTIAL" and r["evidence"]
                for r in relations
            )
            second = await rebuild(conn, repo, snapshot, first)
            after = await read(conn, repo)
            assert first != second
            assert [(d["document_id"], d["content_sha256"]) for d in before] == [
                (d["document_id"], d["content_sha256"]) for d in after
            ]
            assert (await snapshots.published_snapshot(conn, repo))["id"] == snapshot
            with pytest.raises(ValueError, match="pointer changed"):
                await rebuild(conn, repo, snapshot, first)
            assert (
                await conn.fetchval("SELECT count(*) FROM search_index_generations")
                == 2
            )
            with pytest.raises(asyncpg.CheckViolationError, match="immutable"):
                await conn.execute("UPDATE search_documents SET content='{}'")
            with pytest.raises(asyncpg.CheckViolationError, match="immutable"):
                await conn.execute(
                    "UPDATE search_index_generations SET policy_version='changed'"
                )
            with pytest.raises(PermissionError):
                await read_search_documents(conn, repo, allowed_repository_ids=[])
            with pytest.raises(PermissionError):
                await rebuild_search_documents(
                    conn,
                    repo,
                    snapshot,
                    allowed_repository_ids=[],
                    policy_version="test",
                    redact=str,
                    expected_generation_id=second,
                )
            with pytest.raises(ValueError, match="limit"):
                await read_search_documents(
                    conn, repo, allowed_repository_ids=[repo], limit=0
                )
            with pytest.raises(ValueError, match="another repository"):
                await rebuild(conn, uuid4(), snapshot)
            with pytest.raises(ValueError, match="another repository"):
                await rebuild(conn, repo, uuid4())
            other = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="other", display_name="other", source="fixture"
                ),
            )
            other_snapshot = await create(conn, other, ucm_batch_factory(other))
            await validate_snapshot(conn, other_snapshot)
            await publish_snapshot(
                conn, other, other_snapshot, expected_snapshot_id=None
            )
            await rebuild(conn, other, other_snapshot)
            assert {d["snapshot_id"] for d in await read(conn, repo)} == {snapshot}
            new = await create(conn, repo, ucm_batch_factory(repo))
            await validate_snapshot(conn, new)
            await publish_snapshot(conn, repo, new, expected_snapshot_id=snapshot)
            with pytest.raises(LookupError):
                await read(conn, repo)
            with pytest.raises(LookupError):
                await read_search_documents(
                    conn, repo, allowed_repository_ids=[repo], snapshot_id=snapshot
                )
            await rebuild(conn, repo, new)
            assert {d["snapshot_id"] for d in await read(conn, repo)} == {new}
            removed = await jobs.collect_garbage(conn, keep_retired=0)
            assert snapshot in removed["retired"]
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM search_index_generations WHERE snapshot_id=$1",
                    snapshot,
                )
                == 0
            )
            assert {d["snapshot_id"] for d in await read(conn, repo)} == {new}
            assert {d["snapshot_id"] for d in await read(conn, other)} == {
                other_snapshot
            }
        finally:
            await conn.close()

    asyncio.run(scenario())


async def rebuild(
    conn: asyncpg.Connection, repo: UUID, snapshot: UUID, expected: UUID | None = None
) -> UUID:
    return await rebuild_search_documents(
        conn,
        repo,
        snapshot,
        allowed_repository_ids=[repo],
        policy_version="fixture-v1",
        redact=lambda text: text.replace("Static site", "[REDACTED]"),
        expected_generation_id=expected,
    )


async def read(conn: asyncpg.Connection, repo: UUID) -> list[dict]:
    return await read_search_documents(conn, repo, allowed_repository_ids=[repo])


def test_atomic_failure_and_cancel(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        writer = await asyncpg.connect(database_url)
        reader = await asyncpg.connect(database_url)
        task = None
        try:
            repo = await setup(writer)
            snapshot = await create(writer, repo, ucm_batch_factory(repo))
            await validate_snapshot(writer, snapshot)
            await publish_snapshot(writer, repo, snapshot, expected_snapshot_id=None)
            first = await rebuild(writer, repo, snapshot)
            before = await read(reader, repo)

            def fail_policy(text: str) -> str:
                raise RuntimeError("policy unavailable")

            with pytest.raises(RuntimeError, match="policy unavailable"):
                await rebuild_search_documents(
                    writer,
                    repo,
                    snapshot,
                    allowed_repository_ids=[repo],
                    policy_version="failing-v1",
                    redact=fail_policy,
                    expected_generation_id=first,
                )
            assert await read(reader, repo) == before
            await writer.execute("""CREATE FUNCTION pause_search() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN PERFORM pg_sleep(10); RETURN NEW; END; $$;
                CREATE TRIGGER pause_search BEFORE UPDATE ON search_index_publications FOR EACH ROW EXECUTE FUNCTION pause_search();""")
            task = asyncio.create_task(rebuild(writer, repo, snapshot, first))

            async def wait_for_switch() -> None:
                while (
                    await reader.fetchval(
                        "SELECT wait_event FROM pg_stat_activity WHERE pid=$1",
                        writer.get_server_pid(),
                    )
                    != "PgSleep"
                ):
                    if task.done():
                        await task
                        raise AssertionError("publication did not pause")
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_switch(), 5)
            assert await read(reader, repo) == before
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await read(reader, repo) == before
            assert (
                await reader.fetchval("SELECT count(*) FROM search_index_generations")
                == 1
            )
            await writer.execute(
                "DROP TRIGGER pause_search ON search_index_publications; DROP FUNCTION pause_search()"
            )
            await writer.execute("""CREATE FUNCTION fail_search() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'injected failure' USING ERRCODE='23514'; END; $$;
                CREATE TRIGGER fail_search BEFORE UPDATE ON search_index_publications FOR EACH ROW EXECUTE FUNCTION fail_search();""")
            with pytest.raises(asyncpg.CheckViolationError):
                await rebuild(writer, repo, snapshot, first)
            assert await read(reader, repo) == before
            assert (
                await reader.fetchval("SELECT count(*) FROM search_index_generations")
                == 1
            )
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await writer.close()
            await reader.close()

    asyncio.run(scenario())


def test_empty_generations_and_storage_guards(database_url: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            snapshot = await create(conn, repo)
            await validate_snapshot(conn, snapshot)
            await publish_snapshot(conn, repo, snapshot, expected_snapshot_id=None)
            await rebuild(conn, repo, snapshot)
            assert await read(conn, repo) == []
            incomplete = uuid4()
            await conn.execute(
                """INSERT INTO search_index_generations
                (id,repository_id,snapshot_id,projection_version,policy_version,document_count)
                VALUES ($1,$2,$3,'v1','test',1)""",
                incomplete,
                repo,
                snapshot,
            )
            with pytest.raises(asyncpg.CheckViolationError, match="incomplete"):
                await conn.execute(
                    "UPDATE search_index_generations SET sealed=true WHERE id=$1",
                    incomplete,
                )
            with pytest.raises(asyncpg.CheckViolationError, match="sealed"):
                await conn.execute(
                    "UPDATE search_index_publications SET generation_id=$1", incomplete
                )
            for table in (
                "search_documents",
                "search_index_generations",
                "search_index_publications",
            ):
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(f"TRUNCATE {table} CASCADE")
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_concurrent_rebuild_and_pinned_read(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        first = await asyncpg.connect(database_url)
        second = await asyncpg.connect(database_url)
        reader = await asyncpg.connect(database_url)
        try:
            repo = await setup(first)
            snapshot = await create(first, repo, ucm_batch_factory(repo))
            await validate_snapshot(first, snapshot)
            await publish_snapshot(first, repo, snapshot, expected_snapshot_id=None)
            old = await rebuild(first, repo, snapshot)
            async with reader.transaction(isolation="repeatable_read", readonly=True):
                page = await read_search_documents(
                    reader, repo, allowed_repository_ids=[repo], limit=1
                )
                results = await asyncio.wait_for(
                    asyncio.gather(
                        rebuild(first, repo, snapshot, old),
                        rebuild(second, repo, snapshot, old),
                        return_exceptions=True,
                    ),
                    10,
                )
                assert sum(isinstance(r, UUID) for r in results) == 1
                assert sum(isinstance(r, ValueError) for r in results) == 1
                remaining = await read_search_documents(
                    reader,
                    repo,
                    allowed_repository_ids=[repo],
                    after_document_id=page[0]["document_id"],
                )
                assert remaining and all(
                    d["generation_id"] == old for d in page + remaining
                )
            assert all(d["generation_id"] != old for d in await read(reader, repo))
            assert (
                await first.fetchval("SELECT count(*) FROM search_index_generations")
                == 2
            )
        finally:
            await first.close()
            await second.close()
            await reader.close()

    asyncio.run(scenario())


def test_orm_sql_full_and_incremental_projection(
    database_url: str, tmp_path: Path
) -> None:
    from test_jpa_orm_storage import setup as setup_orm

    from code_crawler.java_orm import index_java_orm

    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, assignments = await setup_orm(conn, tmp_path)
            old_snapshot = None
            previous = None
            for _ in range(2):
                result = await index_java_orm(conn, repo, tmp_path, assignments)
                await validate_snapshot(conn, result.snapshot_id)
                await publish_snapshot(
                    conn, repo, result.snapshot_id, expected_snapshot_id=old_snapshot
                )
                await rebuild_search_documents(
                    conn,
                    repo,
                    result.snapshot_id,
                    allowed_repository_ids=[repo],
                    policy_version="mask-users-v1",
                    redact=lambda text: text.replace("users", "[REDACTED]"),
                    expected_generation_id=None,
                )
                documents = await read(conn, repo)
                assert {"ORM_MAPPING", "ORM_QUERY", "SQL_STATEMENT", "SYMBOL"} <= {
                    d["document_type"] for d in documents
                }
                assert all(
                    "users" not in str((d["content"], d["provenance"]))
                    for d in documents
                )
                assert all(
                    d["provenance"]["snapshot_id"] == str(result.snapshot_id)
                    for d in documents
                )
                assert all(
                    d["content"]["redacted_source"] is not None
                    for d in documents
                    if d["document_type"] == "SQL_STATEMENT"
                )
                fingerprints = [
                    (d["document_id"], d["content_sha256"]) for d in documents
                ]
                if previous is not None:
                    assert result.plan.reanalyze == ()
                    assert fingerprints == previous
                previous = fingerprints
                old_snapshot = result.snapshot_id
        finally:
            await conn.close()

    asyncio.run(scenario())
