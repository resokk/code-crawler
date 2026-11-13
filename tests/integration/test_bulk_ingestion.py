import asyncio
import json
from collections.abc import Callable
from uuid import UUID, uuid4

import asyncpg
import pytest

from code_crawler import db, snapshots
from code_crawler.ingestion import UcmBatch, ingest_batch
from code_crawler.ucm import EntityType, SourceFile, Value, logical_id

pytestmark = pytest.mark.integration


async def initialize(conn: asyncpg.Connection) -> tuple[UUID, UUID]:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    repo = await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="org/app", display_name="app", source="fixture"
        ),
    )
    return repo, await create(conn, repo)


async def create(conn: asyncpg.Connection, repo: UUID) -> UUID:
    return await snapshots.create_snapshot(
        conn,
        repo,
        snapshots.SnapshotInput(
            commit_hash="commit", source_fingerprint="a" * 64, dirty=False
        ),
    )


async def staged_count(conn: asyncpg.Connection) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM pg_class WHERE relnamespace=pg_my_temp_schema() AND relname LIKE 'ingest_%'"
    )


def test_two_pass_copy_preserves_full_batch(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snap = await initialize(conn)
            batch = ucm_batch_factory(repo)
            mapping = await ingest_batch(conn, snap, batch)
            assert mapping == {
                entity.id: (snap, entity.id) for entity in batch.entities
            }
            assert await conn.fetchval("SELECT count(*) FROM ucm_entities") == len(
                batch.entities
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_type_refs WHERE role='PARAMETER'"
                )
                == 2
            )
            assert (
                await conn.fetchval(
                    "SELECT name FROM ucm_type_refs WHERE role='PARAMETER' AND position=0"
                )
                == "A"
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_type_refs WHERE target_symbol_id IS NOT NULL"
                )
                == 4
            )
            inputs = await conn.fetch(
                "SELECT value_id FROM ucm_operation_values WHERE direction='INPUT' ORDER BY position"
            )
            assert inputs[0] == inputs[2] and inputs[0] != inputs[1]
            assert (
                await conn.fetchval("SELECT count(*) FROM ucm_relation_candidates") == 1
            )
            assert (
                await conn.fetchval("SELECT resolution FROM ucm_relations") == "PARTIAL"
            )
            assert await conn.fetchval("SELECT count(*) FROM ucm_evidence") == 6
            assert (
                await conn.fetchval("SELECT count(*) FROM ucm_coverage_reasons") == 10
            )
            assert (
                await conn.fetchval(
                    "SELECT literal::text FROM ucm_values WHERE value_kind='LITERAL' AND literal='null'::jsonb"
                )
                == "null"
            )
            assert (
                await conn.fetchval(
                    "SELECT literal #>> '{}' FROM ucm_values WHERE literal <> 'null'::jsonb"
                )
                == "select * from пользователи"
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_values WHERE value_kind <> 'LITERAL' AND literal IS NULL"
                )
                == 2
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_external_references WHERE parameter_type_names IS NULL AND selector_kind='SYMBOL'"
                )
                == 1
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_external_references WHERE parameter_type_names='{}'"
                )
                == 1
            )
            assert (
                await conn.fetchval(
                    "SELECT table_name FROM ucm_external_references WHERE selector_kind='DATABASE'"
                )
                == "Users"
            )
            assert (
                await conn.fetchval(
                    "SELECT http_path FROM ucm_external_references WHERE selector_kind='HTTP'"
                )
                == "/users"
            )
            assert await staged_count(conn) == 0
            assert (
                await conn.fetchval("SELECT state FROM ucm_snapshots WHERE id=$1", snap)
                == "BUILDING"
            )
            with pytest.raises(ValueError, match="empty snapshot"):
                await ingest_batch(conn, snap, batch)
            assert await snapshots.published_snapshot(conn, repo) is None
        finally:
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["copy", "canonical_insert"])
def test_failed_load_rolls_back_and_can_retry(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch], failure: str
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, old = await initialize(conn)
            batch = ucm_batch_factory(repo)
            await ingest_batch(conn, old, batch)
            for state in ("VALIDATING", "READY", "PUBLISHED"):
                await conn.execute(
                    "UPDATE ucm_snapshots SET state=$1 WHERE id=$2", state, old
                )
            await conn.execute(
                "INSERT INTO ucm_repository_publications(repository_id,snapshot_id) VALUES ($1,$2)",
                repo,
                old,
            )
            new = await create(conn, repo)
            attempted = batch
            if failure == "copy":
                entities = list(batch.entities)
                index = next(
                    i for i, e in enumerate(entities) if isinstance(e, SourceFile)
                )
                entities[index] = SourceFile.model_validate(
                    {**entities[index].model_dump(), "name": "invalid\0name"}
                )
                attempted = UcmBatch(repository_id=repo, entities=tuple(entities))
            else:
                await conn.execute("""CREATE FUNCTION fail_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN RAISE EXCEPTION 'injected storage failure' USING ERRCODE='23514'; END; $$;
                    CREATE TRIGGER fail_evidence BEFORE INSERT ON ucm_evidence FOR EACH ROW EXECUTE FUNCTION fail_evidence();""")
            with pytest.raises(asyncpg.PostgresError):
                await ingest_batch(conn, new, attempted)
            assert not conn.is_in_transaction()
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_entities WHERE snapshot_id=$1", new
                )
                == 0
            )
            assert await conn.fetchval(
                "SELECT count(*) FROM ucm_entities WHERE snapshot_id=$1", old
            ) == len(batch.entities)
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            assert await staged_count(conn) == 0
            if failure == "canonical_insert":
                await conn.execute(
                    "DROP TRIGGER fail_evidence ON ucm_evidence; DROP FUNCTION fail_evidence()"
                )
            await ingest_batch(conn, new, batch)
            assert await conn.fetchval(
                "SELECT count(*) FROM ucm_entities WHERE snapshot_id=$1", new
            ) == len(batch.entities)
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_snapshot_guards_empty_batch_and_tampered_models(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snap = await initialize(conn)
            batch = ucm_batch_factory(repo)
            for target, attempted in [
                (uuid4(), batch),
                (snap, ucm_batch_factory(uuid4())),
            ]:
                with pytest.raises(ValueError, match="snapshot"):
                    await ingest_batch(conn, target, attempted)
            async with conn.transaction():
                with pytest.raises(ValueError, match="active transaction"):
                    await ingest_batch(conn, snap, batch)
            assert (
                await ingest_batch(
                    conn, snap, UcmBatch(repository_id=repo, entities=())
                )
                == {}
            )
            assert await staged_count(conn) == 0
            broken = batch.model_copy(
                update={"entities": (*batch.entities, batch.entities[0])}
            )
            with pytest.raises(ValueError, match="duplicate"):
                await ingest_batch(conn, snap, broken)
            await conn.execute(
                "UPDATE ucm_snapshots SET state='VALIDATING' WHERE id=$1", snap
            )
            with pytest.raises(ValueError, match="BUILDING"):
                await ingest_batch(conn, snap, batch)
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_parallel_loads_are_serialized(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        first = await asyncpg.connect(database_url)
        second = await asyncpg.connect(database_url)
        try:
            repo, snap = await initialize(first)
            batch = ucm_batch_factory(repo)
            results = await asyncio.wait_for(
                asyncio.gather(
                    ingest_batch(first, snap, batch),
                    ingest_batch(second, snap, batch),
                    return_exceptions=True,
                ),
                timeout=20,
            )
            assert sum(isinstance(result, dict) for result in results) == 1
            assert sum(isinstance(result, ValueError) for result in results) == 1
            assert await first.fetchval("SELECT count(*) FROM ucm_entities") == len(
                batch.entities
            )
            other = await create(first, repo)
            another = await create(first, repo)
            results = await asyncio.wait_for(
                asyncio.gather(
                    ingest_batch(first, other, batch),
                    ingest_batch(second, another, batch),
                ),
                timeout=20,
            )
            assert all(len(result) == len(batch.entities) for result in results)
        finally:
            await first.close()
            await second.close()

    asyncio.run(scenario())


def test_cancellation_rolls_back_canonical_and_staging_rows(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        writer = await asyncpg.connect(database_url)
        observer = await asyncpg.connect(database_url)
        task = None
        try:
            repo, snap = await initialize(writer)
            await observer.execute("""CREATE FUNCTION delay_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN PERFORM pg_sleep(10); RETURN NEW; END; $$;
                CREATE TRIGGER delay_evidence BEFORE INSERT ON ucm_evidence FOR EACH ROW EXECUTE FUNCTION delay_evidence();""")
            task = asyncio.create_task(
                ingest_batch(writer, snap, ucm_batch_factory(repo))
            )

            async def wait_for_write() -> None:
                while (
                    await observer.fetchval(
                        "SELECT wait_event FROM pg_stat_activity WHERE pid=$1",
                        writer.get_server_pid(),
                    )
                    != "PgSleep"
                ):
                    if task.done():
                        await task
                        raise AssertionError(
                            "writer completed before cancellation point"
                        )
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_write(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert not writer.is_in_transaction()
            assert await writer.fetchval("SELECT count(*) FROM ucm_entities") == 0
            assert await staged_count(writer) == 0
            await observer.execute(
                "DROP TRIGGER delay_evidence ON ucm_evidence; DROP FUNCTION delay_evidence()"
            )
            await ingest_batch(writer, snap, ucm_batch_factory(repo))
        finally:
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await writer.close()
            await observer.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("literal", [0, 42, 1.5, True, False, ""])
def test_copy_preserves_literal_scalars(database_url: str, literal: object) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snap = await initialize(conn)
            value = Value(
                repository_id=str(repo),
                logical_key="literal",
                name="literal",
                id=logical_id(str(repo), EntityType.VALUE, "literal"),
                value_kind="LITERAL",
                literal=literal,
            )
            await ingest_batch(
                conn, snap, UcmBatch(repository_id=repo, entities=(value,))
            )
            actual = json.loads(
                await conn.fetchval("SELECT literal::text FROM ucm_values")
            )
            assert actual == literal and type(actual) is type(literal)
        finally:
            await conn.close()

    asyncio.run(scenario())
