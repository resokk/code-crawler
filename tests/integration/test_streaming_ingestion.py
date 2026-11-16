import asyncio
import tracemalloc
from collections.abc import AsyncIterator, Callable
from uuid import UUID, uuid4

import asyncpg
import pytest
from test_bulk_ingestion import create, initialize, staged_count

from code_crawler.ingestion import UcmBatch, ingest_stream
from code_crawler.ucm import Entity, EntityType, SourceFile, Symbol, logical_id

pytestmark = pytest.mark.integration


async def one_by_one(entities: tuple[Entity, ...]) -> AsyncIterator[tuple[Entity, ...]]:
    for entity in entities:
        yield (entity,)


def test_stream_loads_forward_references_in_any_order(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, first = await initialize(conn)
            batch = ucm_batch_factory(repo)
            expected = {e.id: e for e in batch.entities}
            # One entity per chunk, both orders: every reference points across chunks.
            for snapshot, order in (
                (first, batch.entities),
                (await create(conn, repo), tuple(reversed(batch.entities))),
            ):
                assert await ingest_stream(
                    conn, snapshot, repo, one_by_one(order)
                ) == len(expected)
                stored = await conn.fetch(
                    "SELECT entity_id FROM ucm_entities WHERE snapshot_id=$1", snapshot
                )
                assert {r["entity_id"] for r in stored} == set(expected)
                assert await staged_count(conn) == 0
            with pytest.raises(ValueError, match="empty snapshot"):
                await ingest_stream(conn, first, repo, one_by_one(batch.entities))
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_staging_is_empty_between_chunks(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch]
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snapshot = await initialize(conn)
            entities = tuple(reversed(ucm_batch_factory(repo).entities))
            peak_tables = 0

            async def chunks() -> AsyncIterator[tuple[Entity, ...]]:
                nonlocal peak_tables
                for entity in entities:
                    yield (entity,)
                    tables = await conn.fetch(
                        "SELECT relname FROM pg_class WHERE relnamespace=pg_my_temp_schema() "
                        "AND relkind='r' AND relname LIKE 'ingest_%'"
                    )
                    peak_tables = max(peak_tables, len(tables))
                    for table in tables:
                        assert (
                            await conn.fetchval(
                                f"SELECT count(*) FROM pg_temp.{table['relname']}"
                            )
                            == 0
                        )

            assert await ingest_stream(conn, snapshot, repo, chunks()) == len(entities)
            assert peak_tables > 0
            assert await staged_count(conn) == 0
        finally:
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "fault", ["producer", "dangling", "duplicate", "foreign", "cancel"]
)
def test_stream_faults_leave_snapshot_empty_and_retryable(
    database_url: str, ucm_batch_factory: Callable[[UUID], UcmBatch], fault: str
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snapshot = await initialize(conn)
            entities = ucm_batch_factory(repo).entities
            reached = asyncio.Event()

            async def faulty() -> AsyncIterator[tuple[Entity, ...]]:
                for index, entity in enumerate(entities):
                    if fault == "dangling" and isinstance(entity, SourceFile):
                        continue
                    yield (entity,)
                    if index == 2:
                        if fault == "producer":
                            raise RuntimeError("analyzer crashed")
                        if fault == "duplicate":
                            yield (entity,)
                        if fault == "foreign":
                            yield (ucm_batch_factory(uuid4()).entities[0],)
                        if fault == "cancel":
                            reached.set()
                            await asyncio.sleep(60)

            task = asyncio.create_task(ingest_stream(conn, snapshot, repo, faulty()))
            if fault == "cancel":
                await reached.wait()
                task.cancel()
            expected = {
                "producer": RuntimeError,
                "dangling": asyncpg.ForeignKeyViolationError,
                "duplicate": asyncpg.UniqueViolationError,
                "foreign": ValueError,
                "cancel": asyncio.CancelledError,
            }[fault]
            with pytest.raises(expected):
                await task
            assert not conn.is_in_transaction()
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_entities WHERE snapshot_id=$1", snapshot
                )
                == 0
            )
            assert await staged_count(conn) == 0
            assert await ingest_stream(
                conn, snapshot, repo, one_by_one(entities)
            ) == len(entities)
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_stream_memory_does_not_grow_with_entity_count(database_url: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snapshot = await initialize(conn)

            async def classes(total: int) -> AsyncIterator[tuple[Entity, ...]]:
                for start in range(0, total, 1000):
                    yield tuple(
                        Symbol(
                            repository_id=str(repo),
                            logical_key=f"java:type:app.C{i}",
                            id=logical_id(
                                str(repo), EntityType.SYMBOL, f"java:type:app.C{i}"
                            ),
                            name=f"C{i}",
                            symbol_kind="CLASS",
                            qualified_name=f"app.C{i}",
                        )
                        for i in range(start, start + 1000)
                    )

            peaks = []
            for total in (4_000, 16_000):
                tracemalloc.start()
                assert (
                    await ingest_stream(conn, snapshot, repo, classes(total)) == total
                )
                peaks.append(tracemalloc.get_traced_memory()[1])
                tracemalloc.stop()
                snapshot = await create(conn, repo)
            # Four times the entities must not need anywhere near four times the memory.
            assert peaks[1] < peaks[0] * 1.5, peaks
        finally:
            await conn.close()

    asyncio.run(scenario())
