import asyncio
import json
from uuid import uuid4

import asyncpg
import pytest
from test_publication import create, setup
from test_publication_cli import command

from code_crawler import db, jobs, search, snapshots
from code_crawler.publication import publish_snapshot, validate_snapshot

pytestmark = pytest.mark.integration


async def fixture(conn, factory):
    repo = await setup(conn)
    batch = factory(repo)
    retired = await create(conn, repo, batch)
    await validate_snapshot(conn, retired)
    await publish_snapshot(conn, repo, retired, expected_snapshot_id=None)
    published = await create(conn, repo, batch)
    await validate_snapshot(conn, published)
    await publish_snapshot(conn, repo, published, expected_snapshot_id=retired)
    ready = await create(conn, repo, batch)
    await validate_snapshot(conn, ready)
    validating = await create(conn, repo, batch)
    await conn.execute(
        "UPDATE ucm_snapshots SET state='VALIDATING' WHERE id=$1", validating
    )
    building = await create(conn, repo, batch)
    return repo, {
        "RETIRED": retired,
        "PUBLISHED": published,
        "READY": ready,
        "VALIDATING": validating,
        "BUILDING": building,
    }


async def contents(conn):
    return {
        table: await conn.fetchval(
            f"SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]')::text FROM public.{table} t"
        )
        for table in (
            *jobs._SNAPSHOT_TABLES,
            "ucm_snapshots",
            "ingest_jobs",
            "ucm_repository_publications",
        )
    }


def test_gc_protects_states_and_reports_committed_counts(
    database_url, ucm_batch_factory
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo, ids = await fixture(conn, ucm_batch_factory)
            before = {
                snap: await conn.fetchval(
                    "SELECT count(*) FROM ucm_entities WHERE snapshot_id=$1", snap
                )
                for snap in ids.values()
            }
            report = await jobs.collect_garbage(
                conn, building_older_than_hours=0, keep_retired=0
            )
            assert report["building"] == [ids["BUILDING"]]
            assert report["retired"] == [ids["RETIRED"]]
            assert report["deleted_rows"]["ucm_snapshots"] == 2
            assert (
                report["deleted_rows"]["ucm_entities"]
                == before[ids["BUILDING"]] + before[ids["RETIRED"]]
            )
            assert report["deleted_rows"]["ucm_snapshot_sources"] == 2
            assert report["deleted_rows"]["ucm_snapshot_validations"] == 1
            assert not report["errors"]
            assert {
                r["id"]: r["state"]
                for r in await conn.fetch("SELECT id,state FROM ucm_snapshots")
            } == {ids[state]: state for state in ("PUBLISHED", "READY", "VALIDATING")}
            for state in ("PUBLISHED", "READY", "VALIDATING"):
                assert (
                    await conn.fetchval(
                        "SELECT count(*) FROM ucm_entities WHERE snapshot_id=$1",
                        ids[state],
                    )
                    == before[ids[state]]
                )
            assert (await snapshots.published_snapshot(conn, repo))["id"] == ids[
                "PUBLISHED"
            ]
        finally:
            await conn.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("drift", "diagnostic"),
    [
        ("unknown", "unknown="),
        ("pending", "pending="),
        ("missing", "managed snapshot columns"),
        ("order", "unsafe GC FK order"),
        ("foreign_fk", "unmanaged inbound FK"),
        ("inheritance", "inheritance/partitioning"),
    ],
)
def test_gc_preflight_rejects_schema_drift_without_mutation(
    database_url, ucm_batch_factory, drift, diagnostic
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo, ids = await fixture(conn, ucm_batch_factory)
            job = uuid4()
            await conn.execute(
                "INSERT INTO ingest_jobs(id,repository_id,parameters) VALUES($1,$2,'{}')",
                job,
                repo,
            )
            before = await contents(conn)
            if drift == "unknown":
                await conn.execute(
                    "INSERT INTO schema_migrations(name) VALUES('9999_unknown.sql')"
                )
            elif drift == "pending":
                await conn.execute(
                    "DELETE FROM schema_migrations WHERE name='0019_lexical_search_index.sql'"
                )
            elif drift == "missing":
                await conn.execute(
                    "ALTER TABLE ingest_snapshot_adapters RENAME TO hidden_adapters"
                )
            elif drift == "order":
                await conn.execute(
                    "ALTER TABLE ucm_values ADD CONSTRAINT gc_unsafe_order FOREIGN KEY(snapshot_id,entity_id) REFERENCES ucm_entities(snapshot_id,entity_id)"
                )
            elif drift == "foreign_fk":
                await conn.execute(
                    "CREATE TABLE public.custom_snapshots(snapshot_id uuid REFERENCES ucm_snapshots(id) ON DELETE CASCADE, payload text)"
                )
                await conn.execute(
                    "INSERT INTO custom_snapshots VALUES($1,'keep this')",
                    ids["RETIRED"],
                )
            else:
                await conn.execute(
                    "CREATE TABLE public.custom_entities() INHERITS(public.ucm_entities)"
                )
            with pytest.raises(jobs.GCError, match=diagnostic) as failure:
                await jobs.collect_garbage(
                    conn, building_older_than_hours=0, keep_retired=0
                )
            assert failure.value.report["errors"][0]["stage"] == "preflight"
            assert failure.value.report["deleted_rows"] == {}
            assert (
                failure.value.report["building"]
                == failure.value.report["retired"]
                == []
            )
            if drift == "missing":
                await conn.execute(
                    "ALTER TABLE hidden_adapters RENAME TO ingest_snapshot_adapters"
                )
            assert await contents(conn) == before
            assert (
                await conn.fetchval("SELECT state FROM ingest_jobs WHERE id=$1", job)
                == "RUNNING"
            )
            if drift == "foreign_fk":
                assert (
                    await conn.fetchval("SELECT payload FROM custom_snapshots")
                    == "keep this"
                )
        finally:
            await conn.close()

    asyncio.run(run())


def test_gc_rolls_back_mid_delete_failure_and_redacts_diagnostics(
    database_url, ucm_batch_factory
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo, ids = await fixture(conn, ucm_batch_factory)
            job = uuid4()
            await conn.execute(
                "INSERT INTO ingest_jobs(id,repository_id,parameters) VALUES($1,$2,'{}')",
                job,
                repo,
            )
            await conn.execute("""CREATE FUNCTION public.fail_gc() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF EXISTS(SELECT 1 FROM ucm_entities WHERE snapshot_id=OLD.snapshot_id) THEN
                        RAISE EXCEPTION 'failure was not injected mid-delete';
                    END IF;
                    RAISE EXCEPTION 'PRIVATE_SOURCE_SENTINEL' USING ERRCODE='23503', DETAIL='PRIVATE_SOURCE_SENTINEL';
                END $$;
                CREATE TRIGGER fail_gc BEFORE DELETE ON public.ucm_source_files FOR EACH ROW EXECUTE FUNCTION public.fail_gc();""")
            before = await contents(conn)
            with pytest.raises(jobs.GCError) as failure:
                await jobs.collect_garbage(
                    conn, building_older_than_hours=0, keep_retired=0
                )
            report = failure.value.report
            assert report["errors"][0]["sqlstate"] == "23503"
            assert report["errors"][0]["stage"] == "delete"
            assert (
                report["reaped_jobs"] == report["building"] == report["retired"] == []
            )
            assert report["deleted_rows"] == {}
            assert "PRIVATE_SOURCE_SENTINEL" not in str(failure.value) + json.dumps(
                report
            )
            assert await contents(conn) == before
            code, output = await command(
                database_url, "snapshot", "gc", "--keep-retired", "0"
            )
            assert code != 0 and '"errors"' in output and "23503" in output
            assert "PRIVATE_SOURCE_SENTINEL" not in output
            assert await contents(conn) == before
            await conn.execute("DROP TRIGGER fail_gc ON public.ucm_source_files")
            report = await jobs.collect_garbage(
                conn, building_older_than_hours=0, keep_retired=0
            )
            assert set(report["building"] + report["retired"]) == {
                ids["BUILDING"],
                ids["RETIRED"],
            }
        finally:
            await conn.close()

    asyncio.run(run())


@pytest.mark.parametrize(
    "lock", ["repository", "snapshot", "reader", "search", "running_job"]
)
def test_gc_skips_active_snapshots_then_collects_after_release(
    database_url, ucm_batch_factory, lock
):
    async def run():
        conn = await asyncpg.connect(database_url)
        user = await asyncpg.connect(database_url)
        try:
            repo, ids = await fixture(conn, ucm_batch_factory)
            if lock == "running_job":
                job = await jobs.begin(user, repo, {})
                await jobs.advance(user, job, "PUBLISH", ids["RETIRED"])
                report = await asyncio.wait_for(
                    jobs.collect_garbage(conn, keep_retired=0), 3
                )
                assert report["retired"] == []
                await jobs.finish(user, job)
            else:
                async with user.transaction(readonly=lock in ("reader", "search")):
                    if lock == "repository":
                        await user.fetchval(
                            "SELECT id FROM ucm_repositories WHERE id=$1 FOR UPDATE",
                            repo,
                        )
                    elif lock == "snapshot":
                        await user.fetchval(
                            "SELECT id FROM ucm_snapshots WHERE id=$1 FOR UPDATE",
                            ids["RETIRED"],
                        )
                    elif lock == "reader":
                        await snapshots.pin_snapshot(user, ids["RETIRED"])
                    else:
                        await search.search_text(
                            user, "repo", "A", snapshot_id=ids["RETIRED"]
                        )
                    report = await asyncio.wait_for(
                        jobs.collect_garbage(conn, keep_retired=0), 3
                    )
                    assert report["retired"] == []
                    assert (
                        repo in report["skipped_repositories"]
                        if lock == "repository"
                        else ids["RETIRED"] in report["skipped"]
                    )
            report = await jobs.collect_garbage(conn, keep_retired=0)
            assert report["retired"] == [ids["RETIRED"]]
            assert (await snapshots.published_snapshot(conn, repo))["id"] == ids[
                "PUBLISHED"
            ]
        finally:
            await user.close()
            await conn.close()

    asyncio.run(run())


def test_gc_invalid_inputs_do_not_reap_abandoned_jobs(database_url):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            job = uuid4()
            await conn.execute(
                "INSERT INTO ingest_jobs(id,repository_id,parameters) VALUES($1,$2,'{}')",
                job,
                repo,
            )
            for options in (
                {},
                {"keep_retired": -1},
                {"keep_retired": True},
                {"keep_retired": 1.5},
                {"building_older_than_hours": -1},
                {"building_older_than_hours": float("nan")},
                {"building_older_than_hours": float("inf")},
            ):
                with pytest.raises(ValueError):
                    await jobs.collect_garbage(conn, **options)
            with pytest.raises(ValueError, match="active transaction"):
                await snapshots.pin_snapshot(conn, uuid4())
            async with conn.transaction():
                with pytest.raises(ValueError, match="active transaction"):
                    await jobs.collect_garbage(conn, keep_retired=0)
            assert (
                await conn.fetchval("SELECT state FROM ingest_jobs WHERE id=$1", job)
                == "RUNNING"
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_gc_cancellation_restores_data_and_releases_leases(
    database_url, ucm_batch_factory, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        verifier = await asyncpg.connect(database_url)
        started = asyncio.Event()
        try:
            _, ids = await fixture(conn, ucm_batch_factory)
            before = await contents(conn)

            async def pause_after_delete(connection, selected):
                await connection.execute(
                    "DELETE FROM ucm_coverage_reasons WHERE snapshot_id=ANY($1)",
                    selected,
                )
                started.set()
                await asyncio.Event().wait()

            monkeypatch.setattr(jobs, "_delete_snapshots", pause_after_delete)
            task = asyncio.create_task(jobs.collect_garbage(conn, keep_retired=0))
            try:
                await asyncio.wait_for(started.wait(), 3)
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert not conn.is_in_transaction()
            assert await contents(conn) == before
            assert await verifier.fetchval(
                snapshots._TRY_GC_LEASE, snapshots._SNAPSHOT_LOCK, str(ids["RETIRED"])
            )
            assert await verifier.fetchval(
                "SELECT pg_try_advisory_lock($1)", db._MIGRATION_LOCK
            )
            await verifier.execute("SELECT pg_advisory_unlock($1)", db._MIGRATION_LOCK)
        finally:
            await verifier.close()
            await conn.close()

    asyncio.run(run())


def test_gc_waits_for_migration_and_checks_fresh_state(database_url, ucm_batch_factory):
    async def run():
        conn = await asyncpg.connect(database_url)
        migrator = await asyncpg.connect(database_url)
        task = None
        try:
            await fixture(conn, ucm_batch_factory)
            before = await contents(conn)
            pid = await conn.fetchval("SELECT pg_backend_pid()")
            await migrator.execute("SELECT pg_advisory_lock($1)", db._MIGRATION_LOCK)
            task = asyncio.create_task(jobs.collect_garbage(conn, keep_retired=0))
            async with asyncio.timeout(3):
                while not await migrator.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=$1 AND locktype='advisory' AND NOT granted)",
                    pid,
                ):
                    await asyncio.sleep(0.01)
            await migrator.execute(
                "INSERT INTO schema_migrations(name) VALUES('9999_concurrent.sql')"
            )
            await migrator.execute("SELECT pg_advisory_unlock($1)", db._MIGRATION_LOCK)
            with pytest.raises(jobs.GCError, match="9999_concurrent"):
                await task
            assert await contents(conn) == before
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await migrator.close()
            await conn.close()

    asyncio.run(run())


def test_gc_does_not_reap_its_connections_live_job(database_url, ucm_batch_factory):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo, ids = await fixture(conn, ucm_batch_factory)
            job = await jobs.begin(conn, repo, {})
            await jobs.advance(conn, job, "PUBLISH", ids["RETIRED"])
            report = await jobs.collect_garbage(conn, keep_retired=0)
            assert report["reaped_jobs"] == report["retired"] == []
            assert ids["RETIRED"] in report["skipped"]
            assert (
                await conn.fetchval("SELECT state FROM ingest_jobs WHERE id=$1", job)
                == "RUNNING"
            )
            await jobs.finish(conn, job)
            report = await jobs.collect_garbage(conn, keep_retired=0)
            assert report["retired"] == [ids["RETIRED"]]
        finally:
            await conn.close()

    asyncio.run(run())
