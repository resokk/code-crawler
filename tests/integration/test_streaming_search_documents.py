import asyncio
import json
from uuid import uuid4

import asyncpg
import pytest
from test_publication import create, setup
from test_search_document_storage import read, rebuild

from code_crawler import jobs, publication, search_projection, search_storage, snapshots
from code_crawler.data_security import SecretPolicy

pytestmark = pytest.mark.integration


async def stored(conn, generation):
    return [
        tuple(row)
        for row in await conn.fetch(
            "SELECT document_id,entity_id,document_type,content::text,content_sha256,provenance::text "
            "FROM search_documents WHERE generation_id=$1 ORDER BY document_id",
            generation,
        )
    ]


@pytest.mark.parametrize("action", ["mask", "skip", "reject"])
def test_page_parity_and_security_report(
    database_url, ucm_batch_factory, monkeypatch, action
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            batch = ucm_batch_factory(repo)
            snapshot = await create(conn, repo, batch)
            await publication.validate_snapshot(conn, snapshot)
            # READY remains a valid offline source, without any canonical pointer.
            policy = SecretPolicy(action)
            report = {}
            expected = search_storage._records(
                batch, str, security_policy=policy, report=report
            )
            monkeypatch.setattr(search_projection, "_PAGE_SIZE", 1)

            async def forbidden(*args, **kwargs):
                raise AssertionError("whole-snapshot loader was called")

            monkeypatch.setattr(publication, "load_snapshot_batch", forbidden)
            generation = await search_storage.rebuild_search_documents(
                conn,
                repo,
                snapshot,
                allowed_repository_ids=[repo],
                policy_version="v1",
                redact=str,
                expected_generation_id=None,
                security_policy=policy,
            )
            actual = await stored(conn, generation)
            normalize = lambda rows: sorted(
                (r[0], r[1], r[2], json.loads(r[3]), r[4], json.loads(r[5]))
                for r in rows
            )
            assert normalize(actual) == normalize(expected)
            assert (
                json.loads(
                    await conn.fetchval(
                        "SELECT security_report FROM search_index_generations WHERE id=$1",
                        generation,
                    )
                )
                == report
            )
            assert await snapshots.published_snapshot(conn, repo) is None
        finally:
            await conn.close()

    asyncio.run(run())


def test_partial_copy_failure_cancel_gc_lease_and_stale_publication(
    database_url, ucm_batch_factory, monkeypatch
):
    async def run():
        writer = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        task = None
        try:
            repo = await setup(writer)
            snapshot = await create(writer, repo, ucm_batch_factory(repo))
            await publication.validate_snapshot(writer, snapshot)
            await publication.publish_snapshot(
                writer, repo, snapshot, expected_snapshot_id=None
            )
            first = await rebuild(writer, repo, snapshot)
            before = await read(other, repo)
            monkeypatch.setattr(search_projection, "_PAGE_SIZE", 1)
            original = search_storage.projection_pages
            staged = asyncio.Event()
            resume = asyncio.Event()

            async def pause(conn, selected):
                count = 0
                async for page in original(conn, selected):
                    yield page
                    count += 1
                    if count == 1:
                        staged.set()
                        await resume.wait()

            monkeypatch.setattr(search_storage, "projection_pages", pause)
            task = asyncio.create_task(rebuild(writer, repo, snapshot, first))
            await asyncio.wait_for(staged.wait(), 5)
            assert await read(other, repo) == before
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await read(other, repo) == before
            assert (
                await other.fetchval("SELECT count(*) FROM search_index_generations")
                == 1
            )

            staged.clear()
            task = asyncio.create_task(rebuild(writer, repo, snapshot, first))
            await asyncio.wait_for(staged.wait(), 5)
            newer = await create(other, repo, ucm_batch_factory(repo))
            await publication.validate_snapshot(other, newer)
            await publication.publish_snapshot(
                other, repo, newer, expected_snapshot_id=snapshot
            )
            gc = await jobs.collect_garbage(other, keep_retired=0)
            assert snapshot not in gc["retired"]
            assert await other.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_snapshots WHERE id=$1)", snapshot
            )
            resume.set()
            with pytest.raises(ValueError, match="canonical publication changed"):
                await task
            assert (
                await other.fetchval(
                    "SELECT generation_id FROM search_index_publications WHERE snapshot_id=$1",
                    snapshot,
                )
                == first
            )
            assert (await snapshots.published_snapshot(other, repo))["id"] == newer
            assert (
                snapshot
                in (await jobs.collect_garbage(other, keep_retired=0))["retired"]
            )
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await writer.close()
            await other.close()

    asyncio.run(run())


def test_failure_after_partial_staging_and_budgets(
    database_url, ucm_batch_factory, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            snapshot = await create(conn, repo, ucm_batch_factory(repo))
            await publication.validate_snapshot(conn, snapshot)
            await publication.publish_snapshot(
                conn, repo, snapshot, expected_snapshot_id=None
            )
            first = await rebuild(conn, repo, snapshot)
            before = await read(conn, repo)
            original = search_storage.projection_pages
            monkeypatch.setattr(search_projection, "_PAGE_SIZE", 1)

            async def fail(conn, selected):
                async for page in original(conn, selected):
                    yield page
                    raise asyncpg.CheckViolationError("injected after COPY")

            monkeypatch.setattr(search_storage, "projection_pages", fail)
            with pytest.raises(asyncpg.CheckViolationError):
                await rebuild(conn, repo, snapshot, first)
            assert await read(conn, repo) == before
            monkeypatch.setattr(search_storage, "projection_pages", original)
            monkeypatch.setattr(search_projection, "_CONTEXT_LIMIT", 1)
            with pytest.raises(search_projection.ProjectionBudgetError):
                await rebuild(conn, repo, snapshot, first)
            assert await read(conn, repo) == before
            assert (
                await conn.fetchval("SELECT count(*) FROM search_index_generations")
                == 1
            )
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_class WHERE relnamespace=pg_my_temp_schema() AND relname LIKE 'search_stage_%')"
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_authorization_precedes_connection_and_policy():
    def forbidden(text):
        raise AssertionError("policy called")

    with pytest.raises(PermissionError):
        asyncio.run(
            search_storage.rebuild_search_documents(
                None,
                uuid4(),
                uuid4(),
                allowed_repository_ids=[],
                policy_version="v1",
                redact=forbidden,
                expected_generation_id=None,
            )
        )


def test_all_document_kinds_match_batch(database_url, tmp_path, monkeypatch):
    from test_jpa_orm_storage import setup as setup_orm

    from code_crawler.java_orm import index_java_orm

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo, assignments = await setup_orm(conn, tmp_path)
            result = await index_java_orm(conn, repo, tmp_path, assignments)
            await publication.validate_snapshot(conn, result.snapshot_id)
            batch = await publication.load_snapshot_batch(conn, result.snapshot_id)
            expected = search_storage._records(batch, str)
            monkeypatch.setattr(search_projection, "_PAGE_SIZE", 2)
            # Force adaptive splitting while each individual document still fits.
            monkeypatch.setattr(search_projection, "_CONTEXT_LIMIT", 32)
            generation = await search_storage.rebuild_search_documents(
                conn,
                repo,
                result.snapshot_id,
                allowed_repository_ids=[repo],
                policy_version="v1",
                redact=str,
                expected_generation_id=None,
            )
            actual = await stored(conn, generation)

            def normalize(rows):
                return sorted(
                    (r[0], r[1], r[2], json.loads(r[3]), r[4], json.loads(r[5]))
                    for r in rows
                )

            assert normalize(actual) == normalize(expected)
            assert {r[2] for r in actual} == {
                "SYMBOL",
                "SQL_STATEMENT",
                "DATABASE_OBJECT",
                "ORM_MAPPING",
                "ORM_QUERY",
                "CALL_SUMMARY",
            }
        finally:
            await conn.close()

    asyncio.run(run())


def test_security_skip_aggregate_across_pages(
    database_url, ucm_batch_factory, monkeypatch
):
    from code_crawler.ingestion import UcmBatch
    from code_crawler.ucm import EntityType, OrmQuery, Symbol, logical_id

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            batch = ucm_batch_factory(repo)
            owner = next(e for e in batch.entities if isinstance(e, Symbol))
            queries = tuple(
                OrmQuery(
                    repository_id=str(repo),
                    logical_key=f"q{i}",
                    name=f"q{i}",
                    id=logical_id(str(repo), EntityType.ORM_QUERY, f"q{i}"),
                    owner_symbol_id=owner.id,
                    query_kind="JPQL",
                    text="password='testOnlyCredentialValue123456789'",
                    status="PARTIAL",
                    reasons=("fixture",),
                )
                for i in range(260)
            )
            batch = UcmBatch(repository_id=repo, entities=(*batch.entities, *queries))
            snapshot = await create(conn, repo, batch)
            await publication.validate_snapshot(conn, snapshot)
            expected_report = {}
            expected = search_storage._records(
                batch, str, security_policy=SecretPolicy("skip"), report=expected_report
            )
            monkeypatch.setattr(search_projection, "_PAGE_SIZE", 17)
            generation = await search_storage.rebuild_search_documents(
                conn,
                repo,
                snapshot,
                allowed_repository_ids=[repo],
                policy_version="v1",
                redact=str,
                expected_generation_id=None,
                security_policy=SecretPolicy("skip"),
            )
            assert len(await stored(conn, generation)) == len(expected)
            actual = json.loads(
                await conn.fetchval(
                    "SELECT security_report FROM search_index_generations WHERE id=$1",
                    generation,
                )
            )
            assert actual == expected_report
            assert (
                actual["skipped_documents"] == 260
                and len(actual["skipped_entity_ids"]) == 256
            )
            assert actual["skipped_ids_truncated"]
        finally:
            await conn.close()

    asyncio.run(run())


def test_projection_benchmark_owns_database_and_compares_all_record_fields(
    database_url, tmp_path
):
    from code_crawler.search_projection_benchmark import benchmark

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            before = await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_projection_%'"
            )
            report = await benchmark(database_url, (3,), tmp_path / "benchmark.json")
            assert report["implementation_sha"] and report["postgres"]
            trial = report["trials"][0]
            assert trial["canonical_facts"] == 31 and trial["parity"]
            assert [m["documents"] for m in trial["modes"]] == [6, 6]
            assert all(m["max_rss_kib"] > 0 for m in trial["modes"])
            assert before == await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_projection_%'"
            )
        finally:
            await conn.close()

    asyncio.run(run())
