"""Opt-in PostgreSQL 15 query-plan benchmark in an isolated disposable database."""

import argparse
import asyncio
import json
import logging
import os
import platform
import resource
import statistics
import tempfile
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

import asyncpg

from code_crawler import db, jobs, repos, search, snapshots
from code_crawler.ingestion import UcmBatch, ingest_batch
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.reader import published_reader
from code_crawler.source_adapters import AdapterRegistry, index_sources

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Query:
    sql: str
    arguments: tuple[object, ...]


class RecordingConnection:
    """Observe actual API SQL without including EXPLAIN work in wall-time samples."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn
        self.queries: list[Query] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self.conn, name)

    async def fetch(self, sql: str, *arguments: object) -> list[asyncpg.Record]:
        self.queries.append(Query(sql, arguments))
        return await self.conn.fetch(sql, *arguments)

    async def fetchrow(self, sql: str, *arguments: object) -> asyncpg.Record | None:
        self.queries.append(Query(sql, arguments))
        return await self.conn.fetchrow(sql, *arguments)

    async def fetchval(self, sql: str, *arguments: object) -> object:
        self.queries.append(Query(sql, arguments))
        return await self.conn.fetchval(sql, *arguments)


def fixture_sources(groups: int) -> dict[str, str]:
    """Generate deterministic JDBC calls and duplicate-type ambiguity fixtures."""
    if not 1 <= groups <= 5000:
        raise ValueError("groups must be between 1 and 5000")
    result = {}
    for i in range(groups):
        queries = {
            "load": f"SELECT id, name FROM table_{i} WHERE id=? AND name=?",
            "save": f"UPDATE table_{i} SET name=? WHERE id=?",
            "remove": f"DELETE FROM table_{i} WHERE id=? AND name=?",
            "add": f"INSERT INTO table_{i}(id,name) VALUES(?,?)",
            "other": f"SELECT id FROM other_{i} WHERE id=? AND name=?",
        }
        methods = "\n".join(
            f'''public void {name}(String id,String name) throws Exception {{
PreparedStatement p=conn.prepareStatement("{sql}");
p.setString(1,id);p.setString(2,name);p.execute(); }}'''
            for name, sql in queries.items()
        )
        result[f"Repo{i}.java"] = f"""package bench;
import java.sql.Connection; import java.sql.PreparedStatement;
public class Repo{i} {{ private final Connection conn;
public Repo{i}(Connection c) {{this.conn=c;}} {methods} }}"""
        calls = "".join(f"repo.{method}(id,name);" for method in queries)
        result[f"Service{i}.java"] = f"""package bench; public class Service{i} {{
Repo{i} repo; Service{(i + 1) % groups} next;
public void run(String id,String name) throws Exception {{{calls} next.run(id,name);}}
public void ambiguous(External value) {{value.hit();}} }}"""
    for name in ("a", "b"):
        result[f"copies/{name}/External.java"] = (
            "package bench; public class External {public void hit(){}}"
        )
    return result


def _write_fixture(root: Path, groups: int) -> None:
    for path, content in fixture_sources(groups).items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)


def plan_nodes(plan: dict) -> Iterator[dict]:
    """Walk all child and subplan nodes from a PostgreSQL JSON plan."""
    yield plan
    for child in plan.get("Plans", ()):
        yield from plan_nodes(child)


async def _profile(
    conn: asyncpg.Connection, snapshot_id: UUID, groups: int, repeats: int
) -> dict:
    middle = groups // 2
    target = (
        await search.search_symbols(conn, "benchmark", f"bench.Repo{middle}.load")
    )["items"][0]["id"]
    service = (
        await search.search_symbols(conn, "benchmark", f"bench.Service{middle}.run")
    )["items"][0]["id"]
    call = (await search.find_callers(conn, "benchmark", target))["items"][0][
        "relation_id"
    ]

    async def typed(proxy, relation=False):
        async with published_reader(proxy, "benchmark") as view:
            if relation:
                page = await view.get_relations(
                    target, direction="in", kinds=("CALLS",)
                )
                return [e.model_dump(mode="json") for e in page.items]
            return (await view.get_entity(target)).model_dump(mode="json")

    cases = {
        "symbol_simple": lambda c: search.search_symbols(c, "benchmark", "load"),
        "symbol_signature": lambda c: search.search_symbols(
            c,
            "benchmark",
            f"bench.Repo{middle}.load",
            parameter_types=["String", "String"],
        ),
        "callers": lambda c: search.find_callers(c, "benchmark", target),
        "callees": lambda c: search.find_callees(c, "benchmark", service),
        "executions_owner": lambda c: search.find_sql_executions(
            c, "benchmark", symbol_id=target
        ),
        "executions_page": lambda c: search.find_sql_executions(c, "benchmark"),
        "table_readers": lambda c: search.find_table_readers(
            c, "benchmark", f"table_{middle}"
        ),
        "column_writers": lambda c: search.find_table_writers(
            c, "benchmark", f"table_{middle}", column="name"
        ),
        "trace_out": lambda c: search.trace_dependency(
            c,
            "benchmark",
            service,
            relation_kinds=["CALLS", "EXECUTES_SQL", "EXECUTES_STATEMENT"],
            depth=4,
        ),
        "trace_in": lambda c: search.trace_dependency(
            c, "benchmark", target, direction="in", relation_kinds=["CALLS"], depth=4
        ),
        "evidence": lambda c: search.get_evidence(c, "benchmark", call),
        "typed_entity": lambda c: typed(c),
        "typed_incoming": lambda c: typed(c, True),
    }
    proxy = RecordingConnection(conn)
    results = {}
    for name, run in cases.items():
        for _ in range(2):
            await run(proxy)
        samples = []
        for _ in range(repeats):
            proxy.queries.clear()
            start = time.perf_counter()
            output = await run(proxy)
            samples.append((time.perf_counter() - start) * 1000)
        queries = list(proxy.queries)
        plans = []
        for query in queries:
            raw = await conn.fetchval(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query.sql, *query.arguments
            )
            plan = json.loads(raw)[0]
            plans.append(
                {"sql": query.sql, "arguments": query.arguments, "explain": plan}
            )
        results[name] = {
            "wall_ms": samples,
            "median_wall_ms": statistics.median(samples),
            "sql_execution_ms": sum(p["explain"]["Execution Time"] for p in plans),
            "sql_count": len(plans),
            "plans": plans,
            "result": output,
        }
    return results


async def _phase(
    conn: asyncpg.Connection,
    snapshot_id: UUID,
    groups: int,
    repeats: int,
    batch: UcmBatch | None,
    copies: int,
) -> dict:
    await conn.execute("VACUUM ANALYZE")
    counts = {
        row["entity_type"]: row["count"]
        for row in await conn.fetch(
            "SELECT entity_type,count(*) AS count FROM ucm_entities WHERE snapshot_id=$1 GROUP BY entity_type",
            snapshot_id,
        )
    }
    sizes = [
        dict(row)
        for row in await conn.fetch(
            "SELECT indexrelname,pg_relation_size(indexrelid) AS bytes FROM pg_stat_user_indexes ORDER BY indexrelname"
        )
    ]
    profiles = await _profile(conn, snapshot_id, groups, repeats)
    pending, unknown = await db.schema_state(conn)
    if unknown:
        raise ValueError("unsupported historical benchmark schema")
    cleanup_mode = "explicit_historical_trial" if pending else "snapshot_gc"
    copy_times = []
    gc_times = []
    for attempt in range(copies):
        logger.info("Committed batch copy %s/%s starting", attempt + 1, copies)
        trial = await snapshots.create_snapshot(
            conn,
            batch.repository_id,
            snapshots.SnapshotInput(
                commit_hash="benchmark-copy", source_fingerprint="0" * 64, dirty=False
            ),
        )
        start = time.perf_counter()
        await ingest_batch(conn, trial, batch)
        copy_times.append(time.perf_counter() - start)
        logger.info("Committed batch copy finished in %.2fs", copy_times[-1])
        start = time.perf_counter()
        if pending:
            # This owned disposable DB intentionally lacks index migrations; the
            # production GC must reject that state. Remove only this known trial.
            async with conn.transaction():
                await conn.execute("SET CONSTRAINTS ALL DEFERRED")
                await conn.execute("SET LOCAL code_crawler.gc = 'on'")
                for table in jobs._SNAPSHOT_TABLES:
                    if await conn.fetchval("SELECT to_regclass($1)", "public." + table):
                        await conn.execute(
                            f"DELETE FROM public.{table} WHERE snapshot_id=$1", trial
                        )
                await conn.execute(
                    "DELETE FROM public.ucm_snapshots WHERE id=$1", trial
                )
        else:
            await jobs.collect_garbage(conn, building_older_than_hours=0)
        gc_times.append(time.perf_counter() - start)
        logger.info("Trial cleanup finished in %.2fs", gc_times[-1])
    return {
        "entity_count": sum(counts.values()),
        "counts": counts,
        "index_sizes": sizes,
        "queries": profiles,
        "committed_batch_copy_seconds": copy_times,
        "garbage_collection_seconds": gc_times,
        "cleanup_mode": cleanup_mode,
    }


def _peak_rss_kib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 if platform.system() == "Darwin" else 1)


async def benchmark(
    admin_url: str, groups: int = 200, repeats: int = 7, copies: int = 2
) -> dict:
    """Create and drop only a benchmark-owned PG15 database; return reproducible plans.

    `copies` is the number of committed copy + GC trials per schema phase; 0 skips
    them and never loads the whole snapshot into memory.
    """
    if not 1 <= groups <= 5000 or not 1 <= repeats <= 50 or not 0 <= copies <= 20:
        raise ValueError("invalid benchmark size/repeats/copies")
    admin = await asyncpg.connect(admin_url)
    name = "crawler_benchmark_" + uuid4().hex
    created = False
    conn = None
    try:
        version = int(await admin.fetchval("SHOW server_version_num"))
        if not 150000 <= version < 160000:
            raise ValueError("benchmark requires PostgreSQL 15")
        await admin.execute(f'CREATE DATABASE "{name}"')
        created = True
        url = urlunsplit(urlsplit(admin_url)._replace(path="/" + name))
        conn = await asyncpg.connect(url)
        for migration in await db.begin_migration(conn, init=True):
            if migration < "0018":
                await db.apply_migration(conn, migration)
        await conn.execute("SELECT pg_advisory_unlock_all()")
        with tempfile.TemporaryDirectory(
            prefix="crawler-query-benchmark-"
        ) as directory:
            root = Path(directory)
            await asyncio.to_thread(_write_fixture, root, groups)
            await repos.git("init", cwd=root)
            await repos.git("config", "user.name", "Query Benchmark", cwd=root)
            await repos.git(
                "config", "user.email", "benchmark@example.invalid", cwd=root
            )
            await repos.git("add", ".", cwd=root)
            await repos.git("commit", "-m", "synthetic workload", cwd=root)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="benchmark",
                    display_name="benchmark",
                    source=str(root),
                ),
            )
            start = time.perf_counter()
            indexed = await index_sources(
                conn, repo, root, AdapterRegistry((JavaSourceAdapter(profile="orm"),))
            )
            index_seconds = time.perf_counter() - start
            start = time.perf_counter()
            await validate_snapshot(conn, indexed.snapshot_id)
            validate_seconds = time.perf_counter() - start
            pipeline_rss = _peak_rss_kib()
            await publish_snapshot(
                conn, repo, indexed.snapshot_id, expected_snapshot_id=None
            )
            batch = (
                await load_snapshot_batch(conn, indexed.snapshot_id) if copies else None
            )
            phases = {}
            logger.info("Index complete in %.2fs; profiling before 0018", index_seconds)
            phases["before_0018"] = await _phase(
                conn, indexed.snapshot_id, groups, repeats, batch, copies
            )
            await db.apply_migration(conn, "0018_ucm_query_indexes.sql")
            logger.info("Profiling after 0018")
            phases["after_0018"] = await _phase(
                conn, indexed.snapshot_id, groups, repeats, batch, copies
            )
            for migration in await db.begin_migration(conn):
                await db.apply_migration(conn, migration)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            logger.info("Profiling current schema")
            phases["current"] = await _phase(
                conn, indexed.snapshot_id, groups, repeats, batch, copies
            )
            baseline = phases["before_0018"]["queries"]
            if any(
                phase["queries"][key]["result"] != baseline[key]["result"]
                for phase in phases.values()
                for key in baseline
            ):
                raise ValueError("query results changed between index phases")
            return {
                "server_version": await conn.fetchval("SELECT version()"),
                "settings": {
                    key: await conn.fetchval("SHOW " + key)
                    for key in (
                        "plan_cache_mode",
                        "shared_buffers",
                        "work_mem",
                        "lc_collate",
                    )
                },
                "platform": platform.system() + " " + platform.machine(),
                "groups": groups,
                "repeats": repeats,
                "copies": copies,
                "index_seconds": index_seconds,
                "validate_seconds": validate_seconds,
                # До загрузки целого batch для пробных копий: память самого конвейера.
                "index_validate_peak_rss_kib": pipeline_rss,
                "peak_rss_kib": _peak_rss_kib(),
                "phases": phases,
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
    parser.add_argument("--groups", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--copies", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ.get("BENCHMARK_DATABASE_URL")
    if not url:
        parser.error(
            "BENCHMARK_DATABASE_URL must name a dedicated PostgreSQL 15 admin server"
        )
    report = asyncio.run(benchmark(url, args.groups, args.repeats, args.copies))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, default=str, indent=2) + "\n"
    )
    print(
        f"PG15 benchmark: {report['phases']['current']['entity_count']} entities; report: {args.output}"
    )


if __name__ == "__main__":
    main()
