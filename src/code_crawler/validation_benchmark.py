"""SQL-dense readiness memory benchmark in an owned disposable PostgreSQL 15 DB."""

import argparse
import asyncio
import gc
import hashlib
import json
import logging
import os
import platform
import resource
import time
import tracemalloc
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg

from code_crawler import db, publication, snapshots
from code_crawler.incremental import SourceInput
from code_crawler.ingestion import ingest_stream, progress
from code_crawler.source_evidence import archive_sources
from code_crawler.ucm import (
    CodeEntity,
    DataAccess,
    Entity,
    EntityType,
    SourceFile,
    SqlConstruction,
    SqlFragment,
    SqlIdentifier,
    SqlStatement,
    SqlVariant,
    Symbol,
    logical_id,
)

SOURCE = "select '🌍' from \"Users\"".encode()
logger = logging.getLogger(__name__)


def sql_fixture(repository: UUID, index: int | None = None) -> tuple[Entity, ...]:
    """Four facts per SQL unit; every unit owns independent variants/statements."""
    repo = str(repository)

    def base(kind: EntityType, key: str) -> dict:
        return {
            "repository_id": repo,
            "logical_key": key,
            "name": key,
            "id": logical_id(repo, kind, key),
        }

    if index is None:
        return (
            SourceFile(
                **base(EntityType.SOURCE_FILE, "fixture.sql"),
                path="fixture.sql",
                language="sql",
                content_sha256=hashlib.sha256(SOURCE).hexdigest(),
            ),
            Symbol(
                **base(EntityType.SYMBOL, "Owner"),
                symbol_kind="CLASS",
                qualified_name="Owner",
            ),
        )
    candidate = CodeEntity(
        **base(EntityType.SQL_CANDIDATE, f"candidate:{index}"),
        entity_type=EntityType.SQL_CANDIDATE,
    )
    text = SOURCE.decode()
    construction = SqlConstruction(
        **base(EntityType.SQL_CONSTRUCTION, f"construction:{index}"),
        owner_symbol_id=logical_id(repo, EntityType.SYMBOL, "Owner"),
        variants=(
            SqlVariant(
                candidate_id=candidate.id,
                text=text,
                partial=False,
                fragments=(SqlFragment(kind="STATIC", text=text),),
            ),
        ),
    )
    statement = SqlStatement(
        **base(EntityType.SQL_STATEMENT, f"statement:{index}"),
        candidate_id=candidate.id,
        statement_index=0,
        dialect="postgres",
        text=text,
        text_start=0,
        text_end=len(text),
        operation="SELECT",
        parse_status="COMPLETE",
    )
    access = DataAccess(
        **base(EntityType.DATA_ACCESS, f"access:{index}"),
        statement_id=statement.id,
        object_kind="TABLE",
        access_kind="READ",
        role="source",
        table_name=SqlIdentifier(text="Users", quoted=True, normalized="Users"),
        binding_status="BOUND",
        resolution="UNRESOLVED",
        reason="synthetic SQL name only",
    )
    return candidate, construction, statement, access


async def sql_chunks(repository: UUID, units: int) -> AsyncIterator[tuple[Entity, ...]]:
    yield sql_fixture(repository)
    for start in range(0, units, 250):
        yield await asyncio.to_thread(
            lambda start=start: tuple(
                e
                for i in range(start, min(start + 250, units))
                for e in sql_fixture(repository, i)
            )
        )


async def benchmark(admin_url: str, units: int, *, trace: bool = True) -> dict:
    """Report only readiness timing/traced heap; process RSS includes prior ingestion."""
    if not 1 <= units <= 100_000:
        raise ValueError("units must be between 1 and 100000")
    admin = await asyncpg.connect(admin_url)
    name = "crawler_validation_" + uuid4().hex
    created = False
    conn = None
    try:
        if not 150000 <= int(await admin.fetchval("SHOW server_version_num")) < 160000:
            raise ValueError("benchmark requires PostgreSQL 15")
        await admin.execute(f'CREATE DATABASE "{name}"')
        created = True
        conn = await asyncpg.connect(
            urlunsplit(urlsplit(admin_url)._replace(path="/" + name))
        )
        for migration in await db.begin_migration(conn, init=True):
            await db.apply_migration(conn, migration)
        await conn.execute("SELECT pg_advisory_unlock_all()")
        repository = await snapshots.register_repository(
            conn,
            snapshots.RepositoryInput(
                repository_key="validation",
                display_name="validation",
                source="synthetic",
            ),
        )
        snapshot = await snapshots.create_snapshot(
            conn,
            repository,
            snapshots.SnapshotInput(
                commit_hash="fixture", source_fingerprint="a" * 64, dirty=False
            ),
        )
        await ingest_stream(conn, snapshot, repository, sql_chunks(repository, units))
        file = sql_fixture(repository)[0]
        await archive_sources(
            conn, snapshot, (SourceInput(file, SOURCE),), origin="PROVIDED_BYTES"
        )
        gc.collect()
        completed = 0

        def tick(stage: str, total: int | None) -> None:
            nonlocal completed
            if stage == "Проверка снимка":
                completed += 1
                if completed % 16 == 0:
                    logger.info("Validated slices %d/%s", completed, total)

        token = progress.set(tick)
        if trace:
            tracemalloc.start()
        started = time.perf_counter()
        try:
            count = await publication.validate_snapshot(conn, snapshot)
            seconds = time.perf_counter() - started
            peak = tracemalloc.get_traced_memory()[1] if trace else None
        finally:
            if trace:
                tracemalloc.stop()
            progress.reset(token)
        if count != units * 4 + 2:
            raise ValueError("validation count changed")
        return {
            "units": units,
            "entities": count,
            "sql_entities": units * 3,
            "validation_seconds": seconds,
            "peak_python_bytes": peak,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            / (1024 if platform.system() == "Darwin" else 1),
            "slice_size": publication._SLICE,
            "cache_size": publication._CACHE,
            "server_version": await conn.fetchval("SELECT version()"),
            "settings": {
                key: await conn.fetchval("SHOW " + key)
                for key in ("work_mem", "shared_buffers", "lc_collate")
            },
            "implementation_sha256": await asyncio.to_thread(
                lambda: {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (
                        Path(publication.__file__),
                        Path(publication.__file__).with_name("ingestion.py"),
                        Path(publication.__file__).with_name("snapshot_validation.py"),
                    )
                    if p.exists()
                }
            ),
        }
    finally:
        if conn is not None:
            await conn.close()
        if created:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=int, required=True)
    parser.add_argument("--no-trace", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("BENCHMARK_DATABASE_URL")
    if not url:
        parser.error(
            "BENCHMARK_DATABASE_URL must name a dedicated PostgreSQL 15 admin server"
        )
    report = asyncio.run(benchmark(url, args.units, trace=not args.no_trace))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
