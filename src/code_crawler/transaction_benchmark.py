"""Opt-in B03 comparison: real Java analysis, private database, sampled transaction age."""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import resource
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg

from code_crawler import db, incremental, repos
from code_crawler.incremental import _capture, index_incremental
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.publication import _AUXILIARY, _SUBTYPES, validate_snapshot
from code_crawler.query_benchmark import fixture_sources
from code_crawler.source_adapters import AdapterRegistry


def _write_fixture(root: Path, fixture: dict[str, str]) -> None:
    for path, content in fixture.items():
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content)


def _environment() -> dict:
    return {
        "memory_bytes": os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"),
        "cgroup_memory_max": Path("/sys/fs/cgroup/memory.max").read_text().strip()
        if Path("/sys/fs/cgroup/memory.max").exists()
        else None,
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            None,
        ),
    }


def _implementation_hashes() -> dict[str, str]:
    return {
        n: hashlib.sha256(
            Path(incremental.__file__).with_name(n).read_bytes()
        ).hexdigest()
        for n in ("incremental.py", "snapshots.py")
    }


async def benchmark(admin_url: str, *, groups: int = 199) -> dict:
    """Measure one fresh index, never modifying an existing database or repository."""
    if not 1 <= groups <= 1000:
        raise ValueError("groups must be between 1 and 1000")
    admin = await asyncpg.connect(admin_url)
    name = "crawler_transaction_" + uuid4().hex
    created = False
    conn = observer = None
    try:
        version = await admin.fetchval("SHOW server_version_num")
        if not 150000 <= int(version) < 160000:
            raise ValueError("benchmark requires PostgreSQL 15")
        await admin.execute(
            f"CREATE DATABASE \"{name}\" TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C'"
        )
        created = True
        url = urlunsplit(urlsplit(admin_url)._replace(path="/" + name))
        conn = await asyncpg.connect(url)
        observer = await asyncpg.connect(url)
        for migration in await db.begin_migration(conn, init=True):
            await db.apply_migration(conn, migration)
        await conn.execute("SELECT pg_advisory_unlock_all()")
        repo = UUID("11111111-1111-4111-8111-111111111111")
        await conn.execute(
            "INSERT INTO ucm_repositories(id,repository_key,display_name,source) VALUES($1,'benchmark','benchmark','generated-fixture')",
            repo,
        )
        source_root = Path(incremental.__file__).resolve().parents[2]
        report = {
            "implementation_commit": await repos.git(
                "rev-parse", "HEAD", cwd=source_root
            ),
            "implementation_dirty": bool(
                await repos.git_output(
                    "status",
                    "--porcelain",
                    "--",
                    "src/code_crawler/incremental.py",
                    "src/code_crawler/snapshots.py",
                    cwd=source_root,
                )
            ),
            "implementation_files": await asyncio.to_thread(_implementation_hashes),
            "harness_sha256": await asyncio.to_thread(
                lambda: hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            ),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "postgres_version": await conn.fetchval("SELECT version()"),
            "settings": {
                r["name"]: r["setting"]
                for r in await conn.fetch(
                    "SELECT name,setting FROM pg_settings WHERE name=ANY($1)",
                    [
                        "shared_buffers",
                        "work_mem",
                        "max_connections",
                        "fsync",
                        "synchronous_commit",
                    ],
                )
            },
            "groups": groups,
        }
        report.update(await asyncio.to_thread(_environment))
        fixture = fixture_sources(groups)
        report["files"] = len(fixture)
        report["fixture_sha256"] = hashlib.sha256(
            json.dumps(fixture, sort_keys=True).encode()
        ).hexdigest()
        with tempfile.TemporaryDirectory(prefix="crawler-transaction-") as directory:
            root = Path(directory)
            await asyncio.to_thread(_write_fixture, root, fixture)
            await repos.git("init", cwd=root)
            await repos.git("config", "user.name", "Transaction Benchmark", cwd=root)
            await repos.git(
                "config", "user.email", "benchmark@example.invalid", cwd=root
            )
            await repos.git("add", ".", cwd=root)
            await repos.git("commit", "-m", "fixture", cwd=root)
            registry = AdapterRegistry((JavaSourceAdapter(profile="orm"),))
            start = time.perf_counter()
            captured = await _capture(root, repo, registry.languages)
            prepared = await registry.prepare(captured.sources)
            report["capture_catalog_seconds"] = time.perf_counter() - start
            analyses = []
            max_transaction_age = 0.0
            stop = asyncio.Event()

            async def sample():
                nonlocal max_transaction_age
                while not stop.is_set():
                    age = await observer.fetchval(
                        "SELECT extract(epoch FROM clock_timestamp()-xact_start)::float8 FROM pg_stat_activity WHERE pid=$1",
                        conn.get_server_pid(),
                    )
                    if age is not None:
                        max_transaction_age = max(max_transaction_age, age)
                    try:
                        await asyncio.wait_for(stop.wait(), 0.01)
                    except TimeoutError:
                        pass

            async def analyze(sources):
                analyses.append(conn.is_in_transaction())
                return await prepared(sources)

            analyze.analysis_version = prepared.analysis_version
            sampler = asyncio.create_task(sample())
            start = time.perf_counter()
            try:
                result = await index_incremental(
                    conn,
                    repo,
                    root,
                    analyze,
                    languages=registry.languages,
                    analysis_version=prepared.analysis_version,
                    captured=captured,
                    scopes=prepared.scopes,
                )
            finally:
                stop.set()
                await sampler
            report.update(
                index_seconds=time.perf_counter() - start,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                max_sampled_transaction_seconds=max_transaction_age,
                analysis_calls=len(analyses),
                analysis_calls_in_transaction=sum(analyses),
                preparation_seconds=getattr(result, "preparation_seconds", None),
                write_transaction_seconds=getattr(
                    result, "write_transaction_seconds", None
                ),
                spool_bytes=getattr(result, "spool_bytes", None),
            )
            report["entity_count"] = await conn.fetchval(
                "SELECT count(*) FROM ucm_entities WHERE snapshot_id=$1",
                result.snapshot_id,
            )
            tables = {
                "ucm_entities",
                *_SUBTYPES.values(),
                *_AUXILIARY,
                "ingest_file_dependencies",
                "ingest_file_entities",
            }
            digests = {}
            for table in sorted(tables):
                digests[table] = await conn.fetchval(
                    f"SELECT md5(COALESCE(string_agg((to_jsonb(t)-'snapshot_id')::text,'|' ORDER BY (to_jsonb(t)-'snapshot_id')::text),'')) FROM {table} t WHERE snapshot_id=$1",
                    result.snapshot_id,
                )
            report["canonical_digest"] = hashlib.sha256(
                json.dumps(digests, sort_keys=True).encode()
            ).hexdigest()
            start = time.perf_counter()
            await validate_snapshot(conn, result.snapshot_id)
            report["validation_seconds"] = time.perf_counter() - start
            report["validated"] = True
        return report
    finally:
        if observer is not None:
            await observer.close()
        if conn is not None:
            await conn.close()
        if created:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await admin.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=int, default=199)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(benchmark(os.environ["TEST_DATABASE_URL"], groups=args.groups))
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
