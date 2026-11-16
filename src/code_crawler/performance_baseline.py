"""Opt-in end-to-end PG15 baseline; each trial owns a disposable database/process."""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import platform
import resource
import statistics
import sys
import tempfile
import time
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg

from code_crawler import db, incremental, jobs, repos, snapshots, source_adapters
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.publication import publish_snapshot, validate_snapshot
from code_crawler.query_benchmark import _peak_rss_kib, _profile, fixture_sources
from code_crawler.source_adapters import (
    AdapterRegistry,
    PreparedSourceRegistry,
    index_sources,
)

logger = logging.getLogger(__name__)
PREFIX = "crawler_baseline_"
STAGES = (
    "capture",
    "prepare",
    "analyze",
    "stage",
    "transfer",
    "foreign_keys",
    "archive",
    "index",
    "validation",
    "publication",
    "readers",
    "clone",
    "gc",
)


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def process_metrics() -> dict:
    """Process counters, not host-wide IO or a sum of overlapping stage peaks."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    io = {}
    for line in (_read("/proc/self/io") or "").splitlines():
        key, value = line.split(":", 1)
        io[key] = int(value)
    return {
        "peak_rss_kib": _peak_rss_kib(),
        "user_seconds": usage.ru_utime,
        "system_seconds": usage.ru_stime,
        "major_faults": usage.ru_majflt,
        "minor_faults": usage.ru_minflt,
        "block_inputs": usage.ru_inblock,
        "block_outputs": usage.ru_oublock,
        "proc_io": io,
    }


def distribution(samples: list[float]) -> dict:
    """Describe every sample without pretending a small series is a production P95."""
    if not samples:
        return {"samples": [], "count": 0}
    return {
        "samples": samples,
        "count": len(samples),
        "min": min(samples),
        "max": max(samples),
        "median": statistics.median(samples),
        "mean": statistics.mean(samples),
        "stdev": statistics.stdev(samples) if len(samples) > 1 else 0.0,
    }


async def write_report(path: Path, report: dict) -> None:
    def write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(report, default=str, indent=2) + "\n")
        temporary.replace(path)

    await asyncio.to_thread(write)


async def pg_counters(conn: asyncpg.Connection) -> dict:
    await conn.execute("SELECT pg_stat_clear_snapshot()")
    return dict(
        await conn.fetchrow(
            "SELECT pg_current_wal_insert_lsn()::text AS wal_lsn, "
            "pg_database_size(current_database()) AS database_bytes, "
            "xact_commit,xact_rollback,blks_read,blks_hit,temp_files,temp_bytes, "
            "blk_read_time,blk_write_time,deadlocks,stats_reset "
            "FROM pg_stat_database WHERE datname=current_database()"
        )
    )


class Measurements:
    """Benchmark-local wrappers; production execution and transaction boundaries stay intact."""

    def __init__(self, conn: asyncpg.Connection, output: Path, report: dict) -> None:
        self.conn, self.output, self.report = conn, output, report
        self.active: list[str] = []

    async def measure(self, name: str, function: Any, *args: Any, **kwargs: Any) -> Any:
        self.active.append(name)
        self.report["last_stage"] = name
        self.report["active_stages"] = list(self.active)
        await write_report(self.output, self.report)
        before = await asyncio.to_thread(process_metrics)
        wal = await self.conn.fetchval("SELECT pg_current_wal_insert_lsn()")
        start = time.perf_counter()
        status = "success"
        try:
            return await function(*args, **kwargs)
        except BaseException:
            status = "failed_or_cancelled"
            raise
        finally:
            elapsed = time.perf_counter() - start
            after = await asyncio.to_thread(process_metrics)
            # A cancelled transaction may reject SQL; process counters must still survive.
            wal_bytes = None
            try:
                wal_bytes = int(
                    await self.conn.fetchval(
                        "SELECT pg_wal_lsn_diff(pg_current_wal_insert_lsn(),$1::pg_lsn)",
                        wal,
                    )
                )
            except (asyncpg.PostgresError, asyncpg.InterfaceError):
                pass
            event = {
                "seconds": elapsed,
                "status": status,
                "before": before,
                "after": after,
                "cluster_wal_bytes": wal_bytes,
            }
            self.report["stages"].setdefault(name, []).append(event)
            self.active.pop()
            self.report["active_stages"] = list(self.active)
            await write_report(self.output, self.report)
            logger.info("%s: %.3fs (%s)", name, elapsed, status)

    def wrapper(self, name: str, function: Any) -> Any:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            return await self.measure(name, function, *args, **kwargs)

        return wrapped


def _fixture(root: Path, groups: int) -> dict:
    sources = fixture_sources(groups)
    digest = hashlib.sha256()
    size = 0
    for path, source in sorted(sources.items()):
        raw = source.encode()
        digest.update(path.encode() + b"\0" + raw + b"\0")
        size += len(raw)
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return {
        "generator": "query_benchmark.fixture_sources",
        "groups": groups,
        "files": len(sources),
        "source_bytes": size,
        "sha256": digest.hexdigest(),
        "profile": "java/orm",
        "kind": "synthetic JDBC/calls/duplicate types",
    }


async def run_trial(
    url: str, groups: int, repeats: int, gc_timeout: float, output: Path
) -> dict:
    """Run inside an owned DB. The parent guarantees cleanup even after worker death."""
    if not urlsplit(url).path.removeprefix("/").startswith(PREFIX):
        raise ValueError("worker requires a benchmark-owned database")
    report = {
        "status": "running",
        "stages": {},
        "started_at": datetime.now(UTC).isoformat(),
    }
    conn = await asyncpg.connect(url)
    measurements = Measurements(conn, output, report)
    try:
        report["postgres"] = await conn.fetchval("SELECT version()")
        report["settings"] = {
            name: await conn.fetchval("SHOW " + name)
            for name in (
                "shared_buffers",
                "work_mem",
                "maintenance_work_mem",
                "max_connections",
                "plan_cache_mode",
                "track_io_timing",
                "synchronous_commit",
                "fsync",
                "full_page_writes",
                "wal_level",
                "lc_collate",
            )
        }
        for migration in await db.begin_migration(conn, init=True):
            await db.apply_migration(conn, migration)
        await conn.execute("SELECT pg_advisory_unlock_all()")
        report["migrations"] = [
            r["name"]
            for r in await conn.fetch(
                "SELECT name FROM schema_migrations ORDER BY name"
            )
        ]
        with tempfile.TemporaryDirectory(
            prefix="crawler-baseline-fixture-"
        ) as directory:
            root = Path(directory)
            report["fixture"] = await asyncio.to_thread(_fixture, root, groups)
            await repos.git("init", cwd=root)
            await repos.git("config", "user.name", "Performance Benchmark", cwd=root)
            await repos.git(
                "config", "user.email", "benchmark@example.invalid", cwd=root
            )
            await repos.git("add", ".", cwd=root)
            await repos.git("commit", "-m", "deterministic fixture", cwd=root)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="benchmark",
                    display_name="benchmark",
                    source=str(root),
                ),
            )
            report["pg_before"] = await pg_counters(conn)
            registry = AdapterRegistry((JavaSourceAdapter(profile="orm"),))
            # Patch only the binding actually used by this process. No application hooks.
            with ExitStack() as stack:
                for module, attribute, stage in (
                    (source_adapters, "_capture", "capture"),
                    (AdapterRegistry, "prepare", "prepare"),
                    (PreparedSourceRegistry, "__call__", "analyze"),
                    (incremental, "_stage", "stage"),
                    (incremental, "_transfer", "transfer"),
                    (incremental, "_check", "foreign_keys"),
                    (incremental, "archive_sources", "archive"),
                ):
                    stack.enter_context(
                        patch.object(
                            module,
                            attribute,
                            measurements.wrapper(stage, getattr(module, attribute)),
                        )
                    )
                indexed = await measurements.measure(
                    "index", index_sources, conn, repo, root, registry
                )
            snapshot = indexed.snapshot_id
            report["snapshot_id"] = str(snapshot)
            report["counts"] = {
                r["entity_type"]: r["count"]
                for r in await conn.fetch(
                    "SELECT entity_type,count(*) AS count FROM ucm_entities WHERE snapshot_id=$1 GROUP BY entity_type",
                    snapshot,
                )
            }
            report["entity_count"] = sum(report["counts"].values())
            await measurements.measure("validation", validate_snapshot, conn, snapshot)
            await measurements.measure(
                "publication",
                publish_snapshot,
                conn,
                repo,
                snapshot,
                expected_snapshot_id=None,
            )
            await conn.execute("VACUUM ANALYZE")
            report["queries"] = await measurements.measure(
                "readers", _profile, conn, snapshot, groups, repeats
            )
            # Clone through the real incremental pipeline, never materialize a full UcmBatch.
            trial = await measurements.measure(
                "clone", index_sources, conn, repo, root, registry
            )
            report["gc_snapshot_id"] = str(trial.snapshot_id)

            async def collect() -> dict:
                async with asyncio.timeout(gc_timeout):
                    return await jobs.collect_garbage(conn, building_older_than_hours=0)

            try:
                report["gc"] = await measurements.measure("gc", collect)
            except TimeoutError:
                # Cancellation can interrupt BEGIN before asyncpg enters its context.
                await conn.reset()
                report["failure"] = {"type": "TimeoutError", "stage": "gc"}
            if await snapshots.published_snapshot(conn, repo) != await conn.fetchrow(
                "SELECT * FROM ucm_snapshots WHERE id=$1", snapshot
            ):
                raise ValueError("benchmark changed published reader snapshot")
            check = await _profile(conn, snapshot, groups, 1)
            report["reader_results_unchanged_after_gc"] = all(
                value["result"] == check[key]["result"]
                for key, value in report["queries"].items()
            )
            if not report["reader_results_unchanged_after_gc"]:
                raise ValueError("published reader results changed after GC")
            report["status"] = "failed" if "failure" in report else "success"
    except Exception as error:  # noqa: BLE001 -- persist arbitrary benchmark failures before owned-DB cleanup
        logger.error(
            "Trial failed (%s) at %s", type(error).__name__, report.get("last_stage")
        )
        report["status"] = "failed"
        # Never serialize DSNs or arbitrary server error details.
        report["failure"] = {
            "type": type(error).__name__,
            "stage": report.get("last_stage"),
        }
    finally:
        report["process"] = await asyncio.to_thread(process_metrics)
        try:
            report["pg_after"] = await pg_counters(conn)
            if "pg_before" in report:
                report["cluster_wal_bytes"] = int(
                    await conn.fetchval(
                        "SELECT pg_wal_lsn_diff($1::text::pg_lsn,$2::text::pg_lsn)",
                        report["pg_after"]["wal_lsn"],
                        report["pg_before"]["wal_lsn"],
                    )
                )
            report["relation_stats"] = [
                dict(r)
                for r in await conn.fetch(
                    "SELECT relname,n_live_tup,n_dead_tup,seq_scan,idx_scan, "
                    "pg_total_relation_size(relid) AS total_bytes FROM pg_stat_user_tables ORDER BY relname"
                )
            ]
        except (asyncpg.PostgresError, asyncpg.InterfaceError):
            report["pg_after_unavailable"] = True
        await conn.close()
        report["finished_at"] = datetime.now(UTC).isoformat()
        await write_report(output, report)
    return report


async def _environment() -> dict:
    root = Path(__file__).resolve().parents[2]
    return {
        "implementation_sha": await repos.git("rev-parse", "HEAD", cwd=root),
        "working_tree": await repos.git("status", "--porcelain", cwd=root),
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in (_read("/proc/cpuinfo") or "").splitlines()
                if line.startswith("model name")
            ),
            None,
        ),
        "memory": _read("/proc/meminfo"),
        "cgroup_memory_max": _read("/sys/fs/cgroup/memory.max"),
        "cgroup_cpu_max": _read("/sys/fs/cgroup/cpu.max"),
        "uv_lock_sha256": await asyncio.to_thread(
            lambda: hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
        ),
    }


async def benchmark_suite(
    admin_url: str,
    output: Path,
    *,
    groups: tuple[int, ...] = (199, 499, 1500),
    trials: int = 3,
    repeats: int = 7,
    timeout: float = 1800,
    gc_timeout: float = 120,
) -> dict:
    """Run repeated 400-file trials and one trial per larger scale, checkpointing failures."""
    if (
        not groups
        or any(type(g) is not int or not 1 <= g <= 5000 for g in groups)
        or type(trials) is not int
        or not 1 <= trials <= 10
        or type(repeats) is not int
        or not 1 <= repeats <= 50
        or not 0 < timeout <= 7200
        or not 0 < gc_timeout <= timeout
    ):
        raise ValueError("invalid baseline workload/repeats/timeouts")
    report = {
        "format_version": 1,
        "environment": await _environment(),
        "runs": [],
        "parameters": {
            "groups": groups,
            "trials_first_scale": trials,
            "query_repeats": repeats,
            "trial_timeout_seconds": timeout,
            "gc_timeout_seconds": gc_timeout,
        },
        "limitations": [
            "Synthetic Java/JDBC workload; no production SLO.",
            "Stage index includes nested capture/prepare/analyze/stage/transfer/FK/archive; do not sum overlapping totals.",
            "RSS is a cumulative per-process high-water mark; IO counters are client-process counters.",
            "WAL LSN deltas are cluster-wide; run against an idle dedicated PG15 server.",
            "Database stats can lag and include instrumentation; query samples are warm after VACUUM ANALYZE.",
        ],
    }
    admin = await asyncpg.connect(admin_url)
    try:
        version = int(await admin.fetchval("SHOW server_version_num"))
        if not 150000 <= version < 160000:
            raise ValueError("baseline requires PostgreSQL 15")
        for index, size in enumerate(groups):
            for attempt in range(trials if index == 0 else 1):
                name = PREFIX + uuid4().hex
                await admin.execute(f'CREATE DATABASE "{name}"')
                try:
                    with tempfile.TemporaryDirectory(
                        prefix="crawler-baseline-report-"
                    ) as directory:
                        checkpoint = Path(directory) / "trial.json"
                        worker_url = urlunsplit(
                            urlsplit(admin_url)._replace(path="/" + name)
                        )
                        # A killed worker cannot run TemporaryDirectory cleanup itself.
                        environment = dict(
                            os.environ, BASELINE_WORKER_URL=worker_url, TMPDIR=directory
                        )
                        command = [
                            sys.executable,
                            "-m",
                            "code_crawler.performance_baseline",
                            "--worker",
                            "--groups",
                            str(size),
                            "--repeats",
                            str(repeats),
                            "--gc-timeout",
                            str(gc_timeout),
                            "--output",
                            str(checkpoint),
                        ]
                        process = await asyncio.create_subprocess_exec(
                            *command, env=environment
                        )
                        termination = None
                        try:
                            async with asyncio.timeout(timeout):
                                await process.wait()
                        except TimeoutError:
                            termination = "timeout"
                        finally:
                            if process.returncode is None:
                                process.kill()
                                await process.wait()
                        result = await asyncio.to_thread(
                            lambda checkpoint=checkpoint: (
                                json.loads(checkpoint.read_text())
                                if checkpoint.exists()
                                else {}
                            )
                        )
                        if termination or (
                            process.returncode and result.get("status") != "failed"
                        ):
                            result["status"] = termination or "worker_exit"
                            result["returncode"] = process.returncode
                            result["failure"] = {
                                "type": termination or "signal_or_exit",
                                "stage": result.get("last_stage"),
                            }
                        result.update(groups=size, attempt=attempt + 1)
                        report["runs"].append(result)
                finally:
                    await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
                    await write_report(output, report)
        report["distributions_seconds"] = {
            str(size): {
                stage: distribution(
                    [
                        sum(
                            event["seconds"]
                            for event in run.get("stages", {}).get(stage, [])
                        )
                        for run in report["runs"]
                        if run["groups"] == size
                        and run.get("stages", {}).get(stage)
                        and all(e["status"] == "success" for e in run["stages"][stage])
                    ]
                )
                for stage in STAGES
            }
            for size in groups
        }
        report["status"] = (
            "success"
            if all(r["status"] == "success" for r in report["runs"])
            else "completed_with_failures"
        )
        await write_report(output, report)
        return report
    finally:
        await admin.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--groups", type=int, nargs="+", default=[199, 499, 1500])
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--gc-timeout", type=float, default=120)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        report = asyncio.run(
            run_trial(
                os.environ["BASELINE_WORKER_URL"],
                args.groups[0],
                args.repeats,
                args.gc_timeout,
                args.output,
            )
        )
        if report["status"] != "success":
            raise SystemExit(1)
    else:
        url = os.environ.get("BENCHMARK_DATABASE_URL")
        if not url:
            parser.error(
                "BENCHMARK_DATABASE_URL must name a dedicated PG15 admin server"
            )
        asyncio.run(
            benchmark_suite(
                url,
                args.output,
                groups=tuple(args.groups),
                trials=args.trials,
                repeats=args.repeats,
                timeout=args.timeout,
                gc_timeout=args.gc_timeout,
            )
        )


if __name__ == "__main__":
    main()
