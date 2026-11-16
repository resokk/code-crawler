"""Opt-in end-to-end bulk-load benchmark in a disposable PostgreSQL 15 database."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import platform
import resource
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg

from code_crawler import db, snapshots
from code_crawler.incremental import SourceInput
from code_crawler.ingestion import ingest_stream
from code_crawler.publication import publish_snapshot, validate_snapshot
from code_crawler.reader import published_reader
from code_crawler.source_evidence import archive_sources
from code_crawler.ucm import (
    CallableSignature,
    Certainty,
    Coverage,
    Entity,
    EntityRef,
    EntityType,
    Evidence,
    Position,
    Relation,
    RelationKind,
    Resolution,
    SourceFile,
    SourceRange,
    Symbol,
    callable_key,
    logical_id,
)

SOURCE = b"class Bench {}\n"
logger = logging.getLogger(__name__)


def source_file(repository_id: UUID) -> SourceFile:
    """The fixture's archived evidence source, shared by all generated calls."""
    return SourceFile(
        repository_id=str(repository_id),
        logical_key="Bench.java",
        name="Bench.java",
        id=logical_id(str(repository_id), EntityType.SOURCE_FILE, "Bench.java"),
        path="Bench.java",
        language="java",
        content_sha256=hashlib.sha256(SOURCE).hexdigest(),
    )


def pair(repository_id: UUID, index: int, pairs: int) -> tuple[Symbol, Relation]:
    """Generate a callable and an evidenced forward call, without parsing overhead."""
    repo = str(repository_id)
    signature = CallableSignature()
    key = callable_key("Bench", f"m{index}", signature)
    target_key = callable_key("Bench", f"m{(index + 1) % pairs}", signature)
    location = SourceRange(
        source_file_id=source_file(repository_id).id,
        start=Position(line=1, byte_column=0),
        end=Position(line=1, byte_column=14),
    )
    symbol = Symbol(
        repository_id=repo,
        logical_key=key,
        name=f"m{index}",
        id=logical_id(repo, EntityType.SYMBOL, key),
        symbol_kind="METHOD",
        qualified_name=f"Bench.m{index}",
        owner_key="Bench",
        signature=signature,
        source_range=location,
    )
    relation = Relation(
        repository_id=repo,
        logical_key=f"call:{index}",
        name="CALLS",
        id=logical_id(repo, EntityType.RELATION, f"call:{index}"),
        source_range=location,
        relation_kind=RelationKind.CALLS,
        source=EntityRef(id=symbol.id, entity_type=EntityType.SYMBOL),
        resolution=Resolution(
            status="RESOLVED",
            target=EntityRef(
                id=logical_id(repo, EntityType.SYMBOL, target_key),
                entity_type=EntityType.SYMBOL,
            ),
        ),
        certainty=Certainty.INFERRED,
        evidence=(
            Evidence(
                source_range=location,
                analyzer="bulk-benchmark",
                analyzer_version="1",
                rule="synthetic-call",
                description="Synthetic load fixture, not parsed source",
            ),
        ),
        coverage=Coverage(
            capability="benchmark.calls",
            analyzer_version="1",
            status="PARTIAL",
            reasons=("synthetic fixture",),
        ),
    )
    return symbol, relation


async def chunks(
    repository_id: UUID, pairs: int, chunk_size: int
) -> AsyncIterator[tuple[Entity, ...]]:
    yield (source_file(repository_id),)
    for start in range(0, pairs, chunk_size):
        yield await asyncio.to_thread(
            lambda start=start: tuple(
                entity
                for i in range(start, min(start + chunk_size, pairs))
                for entity in pair(repository_id, i, pairs)
            )
        )
        if (start + chunk_size) % 50_000 == 0:
            logger.info(
                "Transferred %d/%d entities",
                min(start + chunk_size, pairs) * 2 + 1,
                pairs * 2 + 1,
            )


class TimedConnection:
    """Time actual writer SQL; diagnostics are included in end-to-end wall time."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.seconds: dict[str, float] = defaultdict(float)
        self.calls: dict[str, int] = defaultdict(int)
        self.stage_peak_bytes = 0
        self.fk_plan = None
        self.before_analyze_fk_plan = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.conn, name)

    async def execute(self, sql: str, *args: object) -> str:
        if sql.startswith("INSERT INTO ucm_"):
            phase = "insert_select"
            size = await self.conn.fetchval(
                "SELECT COALESCE(sum(pg_total_relation_size(oid)),0)::bigint FROM pg_class "
                "WHERE relnamespace=pg_my_temp_schema() AND relkind='r' AND relname LIKE 'ingest_%'"
            )
            self.stage_peak_bytes = max(self.stage_peak_bytes, size)
        elif sql.startswith("SET CONSTRAINTS"):
            phase = "constraints"
            if self.fk_plan is None:
                self.fk_plan = await self._explain_fk()
        elif sql.startswith("ANALYZE ucm_"):
            phase = "analyze"
            if self.before_analyze_fk_plan is None:
                self.before_analyze_fk_plan = await self._explain_fk()
        else:
            phase = "other_sql"
        started = time.perf_counter()
        try:
            return await self.conn.execute(sql, *args)
        finally:
            self.seconds[phase] += time.perf_counter() - started
            self.calls[phase] += 1

    async def _explain_fk(self) -> list[dict] | None:
        row = await self.conn.fetchrow(
            "SELECT snapshot_id,entity_id,entity_type FROM ucm_entities WHERE entity_type='SYMBOL' LIMIT 1"
        )
        if row is None:
            return None
        return json.loads(
            await self.conn.fetchval(
                "EXPLAIN (FORMAT JSON) SELECT 1 FROM ONLY ucm_entities x "
                "WHERE snapshot_id=$1 AND entity_id=$2 AND entity_type=$3 FOR KEY SHARE OF x",
                row["snapshot_id"],
                row["entity_id"],
                row["entity_type"],
            )
        )

    async def copy_records_to_table(self, *args: object, **kwargs: Any) -> str:
        started = time.perf_counter()
        try:
            return await self.conn.copy_records_to_table(*args, **kwargs)
        finally:
            self.seconds["copy"] += time.perf_counter() - started
            self.calls["copy"] += 1


async def benchmark(
    admin_url: str,
    *,
    pairs: int = 500_000,
    repeats: int = 2,
    locale: str = "C",
    chunk_size: int = 5_000,
    budget_seconds: float = 900,
    output_path: Path | None = None,
) -> dict:
    """Measure committed ingestion, archive, validation and publication on PG15.

    Only databases bearing this invocation's random name are created/dropped.
    No GC trials or index disabling are used. Budget applies to each full trial.
    """
    if (
        not 1 <= pairs <= 1_000_000
        or not 1 <= repeats <= 10
        or not 1 <= chunk_size <= 10_000
        or budget_seconds <= 0
    ):
        raise ValueError("invalid benchmark size/repeats/chunk/budget")
    if locale not in ("C", "en_US.utf8"):
        raise ValueError("locale must be C or en_US.utf8")
    ingestion_sha256 = await asyncio.to_thread(
        lambda: hashlib.sha256(
            Path(__file__).with_name("ingestion.py").read_bytes()
        ).hexdigest()
    )
    admin = await asyncpg.connect(admin_url)
    name = "crawler_bulk_" + uuid4().hex
    created = False
    conn = None
    try:
        if not 150000 <= int(await admin.fetchval("SHOW server_version_num")) < 160000:
            raise ValueError("benchmark requires PostgreSQL 15")
        await admin.execute(
            f"CREATE DATABASE \"{name}\" TEMPLATE template0 LC_COLLATE '{locale}' LC_CTYPE '{locale}'"
        )
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
                repository_key="bulk", display_name="bulk", source="synthetic-benchmark"
            ),
        )
        trials = []

        async def report() -> dict:
            return {
                "server_version": await conn.fetchval("SELECT version()"),
                "platform": platform.system() + " " + platform.machine(),
                "cpu_count": os.cpu_count(),
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                / (1024 if platform.system() == "Darwin" else 1),
                "ingestion_sha256": ingestion_sha256,
                "settings": {
                    key: await conn.fetchval("SHOW " + key)
                    for key in (
                        "lc_collate",
                        "shared_buffers",
                        "work_mem",
                        "temp_file_limit",
                        "plan_cache_mode",
                        "max_wal_size",
                        "checkpoint_timeout",
                        "fsync",
                        "synchronous_commit",
                    )
                },
                "pairs": pairs,
                "chunk_size": chunk_size,
                "budget_seconds": budget_seconds,
                "indexes": [
                    dict(row)
                    for row in await conn.fetch(
                        "SELECT indexrelname,pg_relation_size(indexrelid) AS bytes FROM pg_stat_user_indexes ORDER BY indexrelname"
                    )
                ],
                "trials": trials,
                "requested_trials": repeats,
                "complete": len(trials) == repeats,
                "database_bytes": await conn.fetchval(
                    "SELECT pg_database_size(current_database())"
                ),
            }

        previous = None
        for trial in range(repeats):
            logger.info(
                "Trial %d/%d: %d entities, locale %s",
                trial + 1,
                repeats,
                pairs * 2 + 1,
                locale,
            )
            snapshot = await snapshots.create_snapshot(
                conn,
                repository,
                snapshots.SnapshotInput(
                    commit_hash=f"trial-{trial}",
                    source_fingerprint="a" * 64,
                    dirty=False,
                ),
            )
            proxy = TimedConnection(conn)
            started = time.perf_counter()
            count = await ingest_stream(
                proxy, snapshot, repository, chunks(repository, pairs, chunk_size)
            )
            ingest_seconds = time.perf_counter() - started
            logger.info(
                "Committed ingest %.3fs; SQL phases %s",
                ingest_seconds,
                dict(proxy.seconds),
            )
            step = time.perf_counter()
            await archive_sources(
                conn,
                snapshot,
                (SourceInput(source_file(repository), SOURCE),),
                origin="PROVIDED_BYTES",
            )
            archive_seconds = time.perf_counter() - step
            step = time.perf_counter()
            validated = await validate_snapshot(conn, snapshot)
            validation_seconds = time.perf_counter() - step
            logger.info("Validated all entities in %.3fs", validation_seconds)
            step = time.perf_counter()
            await publish_snapshot(
                conn, repository, snapshot, expected_snapshot_id=previous
            )
            publish_seconds = time.perf_counter() - step
            total = time.perf_counter() - started
            logger.info("Published in %.3fs; full trial %.3fs", publish_seconds, total)
            expected = pair(repository, pairs // 2, pairs)
            async with published_reader(conn, "bulk") as reader:
                for entity in expected:
                    if await reader.get_entity(entity.id) != entity:
                        raise ValueError("published reader changed a generated fact")
            if count != validated or count != pairs * 2 + 1:
                raise ValueError("entity count changed during validation")
            if await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_class WHERE relnamespace=pg_my_temp_schema() AND relname LIKE 'ingest_%')"
            ):
                raise ValueError("staging tables survived commit")
            trials.append(
                {
                    "entities": count,
                    "ingest_seconds": ingest_seconds,
                    "sql_seconds": dict(proxy.seconds),
                    "sql_calls": dict(proxy.calls),
                    "stage_peak_bytes": proxy.stage_peak_bytes,
                    "fk_plan": proxy.fk_plan,
                    "before_analyze_fk_plan": proxy.before_analyze_fk_plan,
                    "archive_seconds": archive_seconds,
                    "validation_seconds": validation_seconds,
                    "publish_seconds": publish_seconds,
                    "total_seconds": total,
                    "budget_passed": total <= budget_seconds,
                }
            )
            previous = snapshot
            result = await report()
            if output_path is not None:
                await asyncio.to_thread(_save_report, output_path, result)
        return result

    finally:
        if conn is not None:
            await conn.close()
        if created:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


def _save_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temporary.write_text(json.dumps(report, indent=2) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=500_000)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--chunk-size", type=int, default=5_000)
    parser.add_argument("--locale", choices=("C", "en_US.utf8"), default="C")
    parser.add_argument("--budget-seconds", type=float, default=900)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("BENCHMARK_DATABASE_URL")
    if not url:
        parser.error(
            "BENCHMARK_DATABASE_URL must name a dedicated PostgreSQL 15 admin server"
        )
    report = asyncio.run(
        benchmark(
            url,
            pairs=args.pairs,
            repeats=args.repeats,
            chunk_size=args.chunk_size,
            locale=args.locale,
            budget_seconds=args.budget_seconds,
            output_path=args.output,
        )
    )
    if not all(trial["budget_passed"] for trial in report["trials"]):
        raise SystemExit("end-to-end budget exceeded; see report")


if __name__ == "__main__":
    main()
