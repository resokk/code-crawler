import asyncio
from collections.abc import Callable
from uuid import UUID, uuid4

import asyncpg
import pytest

from code_crawler import db, snapshots
from code_crawler.ingestion import UcmBatch, ingest_batch
from code_crawler.publication import (
    publish_snapshot,
    rollback_publication,
    validate_snapshot,
)
from code_crawler.ucm import EntityType, logical_id

pytestmark = pytest.mark.integration


async def setup(conn: asyncpg.Connection) -> UUID:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="repo", display_name="app", source="fixture"
        ),
    )


async def create(
    conn: asyncpg.Connection, repo: UUID, batch: UcmBatch | None = None
) -> UUID:
    snap = await snapshots.create_snapshot(
        conn,
        repo,
        snapshots.SnapshotInput(
            commit_hash="commit", source_fingerprint="a" * 64, dirty=False
        ),
    )
    if batch is not None:
        await ingest_batch(conn, snap, batch)
    return snap


def test_validation_publication_and_rollback(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            batch = ucm_batch_factory(repo)
            old = await create(conn, repo, batch)
            assert await validate_snapshot(conn, old) == len(batch.entities)
            assert await validate_snapshot(conn, old) == len(batch.entities)
            assert await snapshots.published_snapshot(conn, repo) is None
            await publish_snapshot(conn, repo, old, expected_snapshot_id=None)
            new = await create(conn, repo, batch)
            await validate_snapshot(conn, new)
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            await publish_snapshot(conn, repo, new, expected_snapshot_id=old)
            assert (await snapshots.published_snapshot(conn, repo))["id"] == new
            assert (
                await conn.fetchval("SELECT state FROM ucm_snapshots WHERE id=$1", old)
                == "RETIRED"
            )
            await rollback_publication(conn, repo, old, expected_snapshot_id=new)
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            assert (
                await conn.fetchval("SELECT state FROM ucm_snapshots WHERE id=$1", new)
                == "RETIRED"
            )
            assert await conn.fetchval("SELECT count(*) FROM ucm_entities") == 2 * len(
                batch.entities
            )
            await publish_snapshot(conn, repo, old, expected_snapshot_id=old)
            with pytest.raises(ValueError, match="pointer changed"):
                await rollback_publication(conn, repo, new, expected_snapshot_id=None)
        finally:
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "problem",
    [
        "missing_extension",
        "missing_evidence",
        "missing_reasons",
        "cardinality",
        "ordinal_gap",
        "type_role",
        "logical_id",
        "scope_cycle",
        "missing_location",
        "missing_candidates",
    ],
)
def test_readiness_gate_rejects_incomplete_storage(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch], problem: str
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            old = await create(conn, repo)
            await validate_snapshot(conn, old)
            await publish_snapshot(conn, repo, old, expected_snapshot_id=None)
            snap = await create(conn, repo, ucm_batch_factory(repo))
            if problem == "missing_extension":
                await conn.execute(
                    "INSERT INTO ucm_entities(snapshot_id,repository_id,entity_id,entity_type,logical_key,name) VALUES ($1,$2,$3,'VALUE','incomplete','incomplete')",
                    snap,
                    repo,
                    logical_id(str(repo), EntityType.VALUE, "incomplete"),
                )
            elif problem == "missing_evidence":
                await conn.execute(
                    "DELETE FROM ucm_evidence WHERE snapshot_id=$1", snap
                )
            elif problem == "missing_reasons":
                await conn.execute(
                    "DELETE FROM ucm_coverage_reasons WHERE snapshot_id=$1", snap
                )
            elif problem == "cardinality":
                await conn.execute(
                    "DELETE FROM ucm_type_refs WHERE snapshot_id=$1 AND role='CALLEE'",
                    snap,
                )
                await conn.execute(
                    "UPDATE ucm_operations SET operation_kind='ASSIGN' WHERE snapshot_id=$1",
                    snap,
                )
            elif problem == "ordinal_gap":
                await conn.execute(
                    "UPDATE ucm_evidence SET ordinal=ordinal+5 WHERE snapshot_id=$1",
                    snap,
                )
            elif problem == "type_role":
                await conn.execute(
                    "UPDATE ucm_type_refs SET owner_id=(SELECT entity_id FROM ucm_relations WHERE snapshot_id=$1) WHERE snapshot_id=$1 AND role='RETURN'",
                    snap,
                )
            elif problem == "logical_id":
                await conn.execute(
                    "UPDATE ucm_entities SET logical_key='changed' WHERE snapshot_id=$1 AND entity_type='VALUE' AND logical_key='text'",
                    snap,
                )
            elif problem == "scope_cycle":
                await conn.execute(
                    "UPDATE ucm_scopes SET parent_scope_id=entity_id WHERE snapshot_id=$1",
                    snap,
                )
            elif problem == "missing_location":
                await conn.execute(
                    "UPDATE ucm_entities SET source_file_id=NULL,start_line=NULL,start_byte_column=NULL,end_line=NULL,end_byte_column=NULL WHERE snapshot_id=$1 AND entity_type='OCCURRENCE'",
                    snap,
                )
            else:
                await conn.execute(
                    "DELETE FROM ucm_relation_candidates WHERE snapshot_id=$1", snap
                )
            with pytest.raises(ValueError):
                await validate_snapshot(conn, snap)
            assert (
                await conn.fetchval("SELECT state FROM ucm_snapshots WHERE id=$1", snap)
                == "VALIDATING"
            )
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_snapshot_validations WHERE snapshot_id=$1)",
                snap,
            )
            with pytest.raises(ValueError, match="READY"):
                await publish_snapshot(conn, repo, snap, expected_snapshot_id=old)
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_publication_guards_and_database_consistency(database_url: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            snap = await create(conn, repo)
            with pytest.raises(ValueError, match="READY"):
                await publish_snapshot(conn, repo, snap, expected_snapshot_id=None)
            await conn.execute(
                "UPDATE ucm_snapshots SET state='VALIDATING' WHERE id=$1", snap
            )
            with pytest.raises(asyncpg.CheckViolationError, match="receipt"):
                await conn.execute(
                    "UPDATE ucm_snapshots SET state='READY' WHERE id=$1", snap
                )
            assert await validate_snapshot(conn, snap) == 0
            with pytest.raises(asyncpg.CheckViolationError, match="pointer"):
                await conn.execute(
                    "UPDATE ucm_snapshots SET state='PUBLISHED' WHERE id=$1", snap
                )
            with pytest.raises(asyncpg.CheckViolationError, match="PUBLISHED"):
                await conn.execute(
                    "INSERT INTO ucm_repository_publications(repository_id,snapshot_id) VALUES ($1,$2)",
                    repo,
                    snap,
                )
            await publish_snapshot(conn, repo, snap, expected_snapshot_id=None)
            for sql in (
                "DELETE FROM ucm_repository_publications",
                "TRUNCATE ucm_repository_publications",
                "UPDATE ucm_snapshots SET state='RETIRED'",
                "UPDATE ucm_snapshot_validations SET entity_count=99",
                "TRUNCATE ucm_snapshot_validations",
            ):
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(sql)
            for target_repo, target in [(uuid4(), snap), (repo, uuid4())]:
                with pytest.raises(ValueError):
                    await publish_snapshot(
                        conn, target_repo, target, expected_snapshot_id=snap
                    )
            other_repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="other", display_name="app", source="other"
                ),
            )
            with pytest.raises(ValueError, match="another repository"):
                await publish_snapshot(
                    conn, other_repo, snap, expected_snapshot_id=None
                )
            async with conn.transaction():
                for call in (
                    validate_snapshot(conn, snap),
                    publish_snapshot(conn, repo, snap, expected_snapshot_id=snap),
                    rollback_publication(conn, repo, snap, expected_snapshot_id=snap),
                ):
                    with pytest.raises(ValueError, match="active transaction"):
                        await call
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_failed_switch_is_atomic_for_readers(database_url: str) -> None:
    async def scenario() -> None:
        writer = await asyncpg.connect(database_url)
        reader = await asyncpg.connect(database_url)
        task = None
        try:
            repo = await setup(writer)
            old = await create(writer, repo)
            new = await create(writer, repo)
            await validate_snapshot(writer, old)
            await validate_snapshot(writer, new)
            await publish_snapshot(writer, repo, old, expected_snapshot_id=None)
            await writer.execute("""CREATE FUNCTION delay_pointer() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN PERFORM pg_sleep(10); RETURN NEW; END; $$;
                CREATE TRIGGER delay_pointer BEFORE UPDATE ON ucm_repository_publications FOR EACH ROW EXECUTE FUNCTION delay_pointer();""")
            task = asyncio.create_task(
                publish_snapshot(writer, repo, new, expected_snapshot_id=old)
            )

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
                        raise AssertionError("no publication pause")
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_switch(), timeout=5)
            assert (await snapshots.published_snapshot(reader, repo))["id"] == old
            assert (
                await reader.fetchval(
                    "SELECT state FROM ucm_snapshots WHERE id=$1", new
                )
                == "READY"
            )
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert (await snapshots.published_snapshot(reader, repo))["id"] == old
            assert (
                await reader.fetchval(
                    "SELECT state FROM ucm_snapshots WHERE id=$1", old
                )
                == "PUBLISHED"
            )
            assert (
                await reader.fetchval(
                    "SELECT state FROM ucm_snapshots WHERE id=$1", new
                )
                == "READY"
            )
            await writer.execute(
                "DROP TRIGGER delay_pointer ON ucm_repository_publications; DROP FUNCTION delay_pointer()"
            )
            await publish_snapshot(writer, repo, new, expected_snapshot_id=old)
            assert (await snapshots.published_snapshot(reader, repo))["id"] == new
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await writer.close()
            await reader.close()

    asyncio.run(scenario())


def test_concurrent_publications_use_expected_pointer(database_url: str) -> None:
    async def scenario() -> None:
        first = await asyncpg.connect(database_url)
        second = await asyncpg.connect(database_url)
        try:
            repo = await setup(first)
            old = await create(first, repo)
            targets = [await create(first, repo), await create(first, repo)]
            for snap in [old, *targets]:
                await validate_snapshot(first, snap)
            await publish_snapshot(first, repo, old, expected_snapshot_id=None)
            results = await asyncio.wait_for(
                asyncio.gather(
                    publish_snapshot(first, repo, targets[0], expected_snapshot_id=old),
                    publish_snapshot(
                        second, repo, targets[1], expected_snapshot_id=old
                    ),
                    return_exceptions=True,
                ),
                timeout=10,
            )
            assert sum(result is None for result in results) == 1
            assert sum(isinstance(result, ValueError) for result in results) == 1
            assert (
                await first.fetchval(
                    "SELECT count(*) FROM ucm_snapshots WHERE state='PUBLISHED'"
                )
                == 1
            )
            assert (
                await first.fetchval(
                    "SELECT count(*) FROM ucm_snapshots WHERE state='READY'"
                )
                == 1
            )
            assert (await snapshots.published_snapshot(first, repo))["id"] in targets
        finally:
            await first.close()
            await second.close()

    asyncio.run(scenario())


def test_validation_receipt_failure_is_retryable(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            batch = ucm_batch_factory(repo)
            snap = await create(conn, repo, batch)
            await conn.execute("""CREATE FUNCTION fail_receipt() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'injected validation failure' USING ERRCODE='23514'; END; $$;
                CREATE TRIGGER fail_receipt BEFORE INSERT ON ucm_snapshot_validations FOR EACH ROW EXECUTE FUNCTION fail_receipt();""")
            with pytest.raises(asyncpg.CheckViolationError):
                await validate_snapshot(conn, snap)
            assert (
                await conn.fetchval("SELECT state FROM ucm_snapshots WHERE id=$1", snap)
                == "VALIDATING"
            )
            assert (
                await conn.fetchval("SELECT count(*) FROM ucm_snapshot_validations")
                == 0
            )
            assert await conn.fetchval("SELECT count(*) FROM ucm_entities") == len(
                batch.entities
            )
            await conn.execute(
                "DROP TRIGGER fail_receipt ON ucm_snapshot_validations; DROP FUNCTION fail_receipt()"
            )
            assert await validate_snapshot(conn, snap) == len(batch.entities)
            await publish_snapshot(conn, repo, snap, expected_snapshot_id=None)
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_concurrent_validation_and_independent_repositories(database_url: str) -> None:
    async def scenario() -> None:
        first = await asyncpg.connect(database_url)
        second = await asyncpg.connect(database_url)
        try:
            repo = await setup(first)
            snap = await create(first, repo)
            assert await asyncio.wait_for(
                asyncio.gather(
                    validate_snapshot(first, snap), validate_snapshot(second, snap)
                ),
                timeout=10,
            ) == [0, 0]
            assert (
                await first.fetchval("SELECT count(*) FROM ucm_snapshot_validations")
                == 1
            )
            other_repo = await snapshots.register_repository(
                first,
                snapshots.RepositoryInput(
                    repository_key="other", display_name="app", source="other"
                ),
            )
            other = await create(first, other_repo)
            await validate_snapshot(second, other)
            await asyncio.wait_for(
                asyncio.gather(
                    publish_snapshot(first, repo, snap, expected_snapshot_id=None),
                    publish_snapshot(
                        second, other_repo, other, expected_snapshot_id=None
                    ),
                ),
                timeout=10,
            )
            assert (
                await first.fetchval(
                    "SELECT count(*) FROM ucm_snapshots WHERE state='PUBLISHED'"
                )
                == 2
            )
        finally:
            await first.close()
            await second.close()

    asyncio.run(scenario())


def test_sql_failure_during_switch_preserves_previous_publication(
    database_url: str,
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            old, new = await create(conn, repo), await create(conn, repo)
            for snap in (old, new):
                await validate_snapshot(conn, snap)
            await publish_snapshot(conn, repo, old, expected_snapshot_id=None)
            await conn.execute("""CREATE FUNCTION fail_pointer() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'injected publication failure' USING ERRCODE='23514'; END; $$;
                CREATE TRIGGER fail_pointer BEFORE UPDATE ON ucm_repository_publications FOR EACH ROW EXECUTE FUNCTION fail_pointer();""")
            with pytest.raises(asyncpg.CheckViolationError):
                await publish_snapshot(conn, repo, new, expected_snapshot_id=old)
            assert not conn.is_in_transaction()
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            assert (
                await conn.fetchval("SELECT state FROM ucm_snapshots WHERE id=$1", old)
                == "PUBLISHED"
            )
            assert (
                await conn.fetchval("SELECT state FROM ucm_snapshots WHERE id=$1", new)
                == "READY"
            )
            await conn.execute(
                "DROP TRIGGER fail_pointer ON ucm_repository_publications; DROP FUNCTION fail_pointer()"
            )
            await publish_snapshot(conn, repo, new, expected_snapshot_id=old)
            assert (await snapshots.published_snapshot(conn, repo))["id"] == new
        finally:
            await conn.close()

    asyncio.run(scenario())
