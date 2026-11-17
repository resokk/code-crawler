"""Opt-in batch/stream parity and fresh-process RSS benchmark in owned PG15 databases."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import platform
import resource
import sys
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg

from code_crawler import (
    db,
    publication,
    repos,
    search_projection,
    search_storage,
    snapshots,
)
from code_crawler.bulk_benchmark import SOURCE, pair, source_file
from code_crawler.incremental import SourceInput
from code_crawler.ingestion import ingest_stream
from code_crawler.source_evidence import archive_sources
from code_crawler.ucm import CodeEntity, Entity, EntityType, logical_id

logger = logging.getLogger(__name__)


def fixture(repository: UUID, start: int, end: int, units: int) -> tuple[Entity, ...]:
    """Ten facts/unit: evidenced ring callable/call plus eight non-document candidates."""
    result = []
    for index in range(start, end):
        symbol, relation = pair(repository, index, units)
        result.extend((symbol, relation))
        for extra in range(8):
            key = f"candidate:{index}:{extra}"
            result.append(
                CodeEntity(
                    repository_id=str(repository),
                    entity_type=EntityType.SQL_CANDIDATE,
                    id=logical_id(str(repository), EntityType.SQL_CANDIDATE, key),
                    logical_key=key,
                    name=key,
                    source_range=symbol.source_range,
                )
            )
    return tuple(result)


async def chunks(repository: UUID, units: int) -> AsyncIterator[tuple[Entity, ...]]:
    yield (source_file(repository),)
    for start in range(0, units, 100):
        yield await asyncio.to_thread(
            fixture, repository, start, min(start + 100, units), units
        )


def fingerprint(rows: list[tuple]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda r: r[0]):
        digest.update((search_storage._json(row) + "\n").encode())
    return digest.hexdigest()


async def worker(url: str, repository: UUID, snapshot: UUID, mode: str) -> dict:
    if not urlsplit(url).path.removeprefix("/").startswith("crawler_projection_"):
        raise ValueError("projection benchmark requires its own database")
    conn = await asyncpg.connect(url)
    try:
        started = time.perf_counter()
        if mode == "batch":
            batch = await publication.load_snapshot_batch(conn, snapshot)
            rows = await asyncio.to_thread(search_storage._records, batch, str)
            seconds = time.perf_counter() - started
            digest = await asyncio.to_thread(fingerprint, rows)
            count = len(rows)
        else:
            generation = await search_storage.rebuild_search_documents(
                conn,
                repository,
                snapshot,
                allowed_repository_ids=[repository],
                policy_version="benchmark-v1",
                redact=str,
                expected_generation_id=None,
            )
            seconds = time.perf_counter() - started
            digest = hashlib.sha256()
            count = 0
            after = ""
            while True:
                rows = await conn.fetch(
                    "SELECT document_id,entity_id,document_type,content,content_sha256,provenance "
                    "FROM search_documents WHERE generation_id=$1 AND document_id>$2 "
                    "ORDER BY document_id LIMIT 200",
                    generation,
                    after,
                )
                if not rows:
                    break
                for row in rows:
                    normalized = (
                        *row[:3],
                        search_storage._json(json.loads(row[3])),
                        row[4],
                        search_storage._json(json.loads(row[5])),
                    )
                    digest.update((search_storage._json(normalized) + "\n").encode())
                count += len(rows)
                after = rows[-1]["document_id"]
            digest = digest.hexdigest()
        return {
            "mode": mode,
            "seconds": seconds,
            "documents": count,
            "all_record_fields_sha256": digest,
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            / (1024 if platform.system() == "Darwin" else 1),
        }
    finally:
        await conn.close()


async def benchmark(admin_url: str, units: tuple[int, ...], output: Path) -> dict:
    if not units or any(not 1 <= n <= 150000 for n in units):
        raise ValueError("units must be between 1 and 150000")
    root = Path(__file__).resolve().parents[2]
    report = {
        "implementation_sha": await repos.git("rev-parse", "HEAD", cwd=root),
        "working_tree": await repos.git("status", "--porcelain", cwd=root),
        "python": sys.version,
        "platform": platform.platform(),
        "trials": [],
        "fixture": "10 UCM facts/unit: ring callable/CALLS with original INFERRED Evidence/PARTIAL Coverage, eight non-document SQL candidates; one archived SourceFile",
        "limits": {
            "root_page": search_projection._PAGE_SIZE,
            "context_facts": search_projection._CONTEXT_LIMIT,
            "copy_bytes": search_storage._COPY_BYTES,
        },
    }
    admin = await asyncpg.connect(admin_url)
    try:
        if not 150000 <= int(await admin.fetchval("SHOW server_version_num")) < 160000:
            raise ValueError("benchmark requires PostgreSQL 15")
        report["postgres"] = await admin.fetchval("SELECT version()")
        report["settings"] = {
            name: await admin.fetchval("SHOW " + name)
            for name in (
                "work_mem",
                "shared_buffers",
                "fsync",
                "synchronous_commit",
                "lc_collate",
            )
        }
        for size in units:
            name = "crawler_projection_" + uuid4().hex
            await admin.execute(f'CREATE DATABASE "{name}"')
            conn = None
            try:
                url = urlunsplit(urlsplit(admin_url)._replace(path="/" + name))
                conn = await asyncpg.connect(url)
                for migration in await db.begin_migration(conn, init=True):
                    await db.apply_migration(conn, migration)
                await conn.execute("SELECT pg_advisory_unlock_all()")
                repository = await snapshots.register_repository(
                    conn,
                    snapshots.RepositoryInput(
                        repository_key="projection",
                        display_name="projection",
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
                logger.info("Ingesting %d facts", size * 10 + 1)
                await ingest_stream(
                    conn, snapshot, repository, chunks(repository, size)
                )
                await archive_sources(
                    conn,
                    snapshot,
                    (SourceInput(source_file(repository), SOURCE),),
                    origin="PROVIDED_BYTES",
                )
                await publication.validate_snapshot(conn, snapshot)
                await publication.publish_snapshot(
                    conn, repository, snapshot, expected_snapshot_id=None
                )
                trial = {"units": size, "canonical_facts": size * 10 + 1, "modes": []}
                report["trials"].append(trial)
                for mode in ("batch", "stream"):
                    logger.info(
                        "Measuring %s projection (%d facts)", mode, size * 10 + 1
                    )
                    with tempfile.TemporaryDirectory(
                        prefix="crawler-projection-result-"
                    ) as directory:
                        result = Path(directory) / "worker.json"
                        process = await asyncio.create_subprocess_exec(
                            sys.executable,
                            "-m",
                            "code_crawler.search_projection_benchmark",
                            "--worker",
                            mode,
                            "--repository",
                            str(repository),
                            "--snapshot",
                            str(snapshot),
                            "--output",
                            str(result),
                            env=dict(os.environ, PROJECTION_WORKER_URL=url),
                        )
                        try:
                            async with asyncio.timeout(1800):
                                code = await process.wait()
                        finally:
                            if process.returncode is None:
                                process.kill()
                                await process.wait()
                        if code:
                            raise RuntimeError("projection benchmark worker failed")
                        trial["modes"].append(
                            await asyncio.to_thread(
                                lambda result=result: json.loads(result.read_text())
                            )
                        )
                trial["parity"] = (
                    trial["modes"][0]["documents"]
                    == trial["modes"][1]["documents"]
                    == size * 2
                    and trial["modes"][0]["all_record_fields_sha256"]
                    == trial["modes"][1]["all_record_fields_sha256"]
                )
                if not trial["parity"]:
                    raise ValueError("projection benchmark parity failed")
            finally:
                if conn is not None:
                    await conn.close()
                await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
                await _save(output, report)
        if len(report["trials"]) >= 2:
            peaks = [t["modes"][1]["max_rss_kib"] for t in report["trials"]]
            report["stream_peak_rss_growth"] = max(peaks) / min(peaks)
            report["memory_acceptance_passed"] = report["stream_peak_rss_growth"] < 1.5
            if not report["memory_acceptance_passed"]:
                raise ValueError("stream projection RSS grew with independent facts")
        await _save(output, report)
        return report
    finally:
        await admin.close()


async def _save(path: Path, report: dict) -> None:
    def save():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n")

    await asyncio.to_thread(save)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--units", type=int, nargs="+", default=[14143, 100001])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", choices=("batch", "stream"))
    parser.add_argument("--repository", type=UUID)
    parser.add_argument("--snapshot", type=UUID)
    args = parser.parse_args()
    if args.worker:
        report = asyncio.run(
            worker(
                os.environ["PROJECTION_WORKER_URL"],
                args.repository,
                args.snapshot,
                args.worker,
            )
        )
        asyncio.run(_save(args.output, report))
    else:
        url = os.environ.get("BENCHMARK_DATABASE_URL")
        if not url:
            parser.error("BENCHMARK_DATABASE_URL must name a dedicated PG15 server")
        asyncio.run(benchmark(url, tuple(args.units), args.output))


if __name__ == "__main__":
    main()
