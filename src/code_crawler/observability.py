"""Bounded task-local operational counters and repository-scoped redacted reports."""

from __future__ import annotations

import asyncio
import logging
import resource
import sys
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from uuid import UUID

import asyncpg

from code_crawler import snapshots

STAGES = frozenset(
    (
        "index",
        "analyze",
        "prepare",
        "stage",
        "transfer",
        "fk",
        "validate",
        "publish",
        "gc",
        "search",
        "db",
    )
)
_LOG = logging.getLogger(__name__)


@dataclass
class Counter:
    calls: int = 0
    errors: int = 0
    seconds: float = 0
    rows: int = 0
    truncated: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class Observation:
    counters: dict[str, Counter] = field(default_factory=dict)

    def counter(self, stage: str) -> Counter:
        if stage not in STAGES:
            raise ValueError("unknown operational stage")
        return self.counters.setdefault(stage, Counter())

    def query(self, event: object) -> None:
        counter = self.counter("db")
        counter.calls += 1
        counter.seconds += event.elapsed
        counter.errors += int(event.exception is not None)


_current: ContextVar[Observation | None] = ContextVar("observation", default=None)


@contextmanager
def span(stage: str) -> Iterator[None]:
    """Time a fixed stage without retaining arguments or exception details."""
    recorder = _current.get()
    if recorder is None:
        yield
        return
    counter = recorder.counter(stage)
    started = time.perf_counter()
    counter.calls += 1
    try:
        yield
    except BaseException:
        counter.errors += 1
        raise
    finally:
        counter.seconds += time.perf_counter() - started


def timed(stage: str) -> Callable:
    """Instrument an async stage when an operation recorder is active."""
    if stage not in STAGES:
        raise ValueError("unknown operational stage")

    def decorate(run: Callable) -> Callable:
        @wraps(run)
        async def wrapped(*args, **kwargs):
            with span(stage):
                return await run(*args, **kwargs)

        return wrapped

    return decorate


def rows(stage: str, count: int) -> None:
    """Count processed rows, never row values."""
    if (recorder := _current.get()) is not None:
        recorder.counter(stage).rows += max(0, count)


def cache(status: str) -> None:
    """Count known resolver outcomes without cache identities or reasons."""
    if (recorder := _current.get()) is not None:
        counter = recorder.counter("search")
        counter.cache_hits += int(status == "HIT")
        counter.cache_misses += int(status == "MISS")


def response(result: dict) -> None:
    """Count returned items and explicit truncation, without traversing source data."""
    if (recorder := _current.get()) is not None:
        counter = recorder.counter("search")
        for key in ("items", "candidates"):
            if isinstance(result.get(key), list):
                counter.rows += len(result[key])
        counter.truncated += int(result.get("truncated") is True)


async def persist(
    conn: asyncpg.Connection,
    recorder: Observation,
    repository_ids: tuple[UUID | None, ...],
    job_id: UUID | None = None,
    attempt: int = 1,
) -> None:
    """Persist only after canonical transactions, in an independent transaction."""
    if conn.is_in_transaction():
        raise ValueError("metrics require a free connection")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak *= 1 if sys.platform == "darwin" else 1024
    records = [
        (
            repo,
            job_id,
            attempt,
            stage,
            c.calls,
            c.errors,
            c.seconds,
            c.rows,
            c.truncated,
            c.cache_hits,
            c.cache_misses,
            peak,
        )
        for repo in dict.fromkeys(repository_ids)
        for stage, c in sorted(recorder.counters.items())
    ]
    async with conn.transaction():
        await conn.execute("SET LOCAL lock_timeout = '250ms'")
        await conn.execute("SET LOCAL statement_timeout = '2s'")
        await conn.executemany(
            "INSERT INTO operational_observations "
            "(repository_id,job_id,attempt,stage,calls,errors,seconds,rows,truncated,"
            "cache_hits,cache_misses,peak_rss_bytes) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)",
            records,
        )


@asynccontextmanager
async def recording(
    conn: asyncpg.Connection,
    repository_ids: tuple[UUID | None, ...],
    job_id: UUID | None = None,
    attempt: int = 1,
    repository_keys: tuple[str, ...] = (),
) -> AsyncIterator[Observation]:
    """Collect independently of immutable facts; telemetry failures cannot mask work."""
    recorder = Observation()
    token = _current.set(recorder)
    try:
        with (
            conn.query_logger(recorder.query)
            if hasattr(conn, "query_logger")
            else nullcontext()
        ):
            yield recorder
    finally:
        _current.reset(token)
        await asyncio.sleep(0)
        try:
            if repository_keys:
                repository_ids = tuple(
                    row["id"]
                    for row in await conn.fetch(
                        "SELECT id FROM ucm_repositories WHERE repository_key=ANY($1::text[])",
                        list(repository_keys),
                        timeout=2,
                    )
                )
            await persist(conn, recorder, repository_ids, job_id, attempt)
        except Exception:  # noqa: BLE001 - telemetry must not replace application errors
            _LOG.warning("operational metrics unavailable")


async def report(
    conn: asyncpg.Connection,
    repository_key: str,
    *,
    days: int = 7,
    job_id: UUID | None = None,
) -> dict:
    """Read bounded numeric operational/coverage aggregates for one repository.

    Privileged library API: public transports must authorize monitor membership first.
    """
    if type(days) is not int or not 1 <= days <= 30:
        raise ValueError("days must be between 1 and 30")
    if not conn.is_in_transaction():
        raise ValueError("monitoring requires a read transaction")
    repository_id = await conn.fetchval(
        "SELECT id FROM ucm_repositories WHERE repository_key=$1", repository_key
    )
    if repository_id is None:
        raise ValueError("repository not found")
    metrics = await conn.fetch(
        "SELECT stage, count(*) AS observations, sum(calls)::bigint AS calls, sum(errors)::bigint AS errors, "
        "sum(rows)::bigint AS rows, sum(truncated)::bigint AS truncated, sum(cache_hits)::bigint AS cache_hits, "
        "sum(cache_misses)::bigint AS cache_misses, max(peak_rss_bytes) AS peak_rss_bytes, "
        "sum(seconds) AS seconds, percentile_cont(0.5) WITHIN GROUP (ORDER BY seconds) AS p50_seconds, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY seconds) AS p95_seconds, "
        "count(DISTINCT job_id) AS jobs, max(attempt) AS max_attempt, "
        "count(*) FILTER (WHERE job_id IS NOT NULL AND attempt>1) AS retry_observations "
        "FROM operational_observations WHERE repository_id=$1 "
        "AND recorded_at >= now() - $2 * interval '1 day' AND ($3::uuid IS NULL OR job_id=$3) GROUP BY stage ORDER BY stage LIMIT 32",
        repository_id,
        days,
        job_id,
    )
    snapshot_id = await conn.fetchval(
        "SELECT snapshot_id FROM ucm_repository_publications WHERE repository_id=$1",
        repository_id,
    )
    coverage: dict = {
        "snapshot_id": str(snapshot_id) if snapshot_id else None,
        "status": "AVAILABLE" if snapshot_id else "NO_PUBLICATION",
    }
    if snapshot_id:
        await snapshots.pin_snapshot(conn, snapshot_id)
        groups = await conn.fetch(
            "SELECT a.adapter_key, c.capability, c.status, count(*) AS files "
            "FROM ucm_source_analyses a JOIN ucm_source_analysis_capabilities c "
            "ON c.snapshot_id=a.snapshot_id AND c.analysis_id=a.entity_id "
            "WHERE a.snapshot_id=$1 GROUP BY a.adapter_key,c.capability,c.status "
            "ORDER BY a.adapter_key,c.capability,c.status LIMIT 129",
            snapshot_id,
        )
        coverage["truncated"] = len(groups) > 128
        # Adapter and capability names are source-producer metadata; return only
        # bounded labels, never free-form diagnostic messages/reasons.
        coverage["groups"] = [dict(row) for row in groups[:128]]
        counts = await conn.fetchrow(
            "SELECT count(*) AS reported, count(*) FILTER (WHERE status='COMPLETE') AS complete "
            "FROM ucm_source_analysis_capabilities WHERE snapshot_id=$1",
            snapshot_id,
        )
        coverage["reported_capabilities"] = counts["reported"]
        coverage["complete_ratio"] = (
            counts["complete"] / counts["reported"] if counts["reported"] else None
        )
        coverage["files"] = await conn.fetchrow(
            "SELECT (SELECT count(*) FROM ucm_source_files WHERE snapshot_id=$1) AS total, "
            "(SELECT count(*) FROM ucm_source_analyses WHERE snapshot_id=$1) AS analyzed",
            snapshot_id,
        )
        coverage["files"] = dict(coverage["files"])
        coverage["unknown_files"] = (
            coverage["files"]["total"] - coverage["files"]["analyzed"]
        )
        adapters = await conn.fetch(
            "SELECT adapter_key,count(*) AS files FROM ucm_source_analyses "
            "WHERE snapshot_id=$1 GROUP BY adapter_key ORDER BY adapter_key LIMIT 129",
            snapshot_id,
        )
        coverage["adapters"] = [dict(row) for row in adapters[:128]]
        coverage["truncated"] |= len(adapters) > 128
        coverage["unreported_capabilities"] = "UNKNOWN"
        coverage["reason_categories"] = [
            dict(row)
            for row in await conn.fetch(
                "SELECT CASE WHEN lower(reason) LIKE '%unresolv%' THEN 'UNRESOLVED' "
                "WHEN lower(reason) LIKE '%unsupport%' THEN 'UNSUPPORTED' "
                "WHEN lower(reason) LIKE '%syntax%' OR lower(reason) LIKE '%pars%' THEN 'PARSER_LIMITATION' "
                "WHEN lower(reason) LIKE '%dynamic%' THEN 'DYNAMIC' ELSE 'OTHER_PARTIAL' END AS category, "
                "count(*) AS count FROM ucm_source_analysis_reasons WHERE snapshot_id=$1 "
                "GROUP BY 1 ORDER BY 1",
                snapshot_id,
            )
        ]
        coverage["diagnostics"] = [
            dict(row)
            for row in await conn.fetch(
                "SELECT a.adapter_key,d.severity,count(*) AS count FROM ucm_source_diagnostics d "
                "JOIN ucm_source_analyses a ON a.snapshot_id=d.snapshot_id AND a.entity_id=d.analysis_id "
                "WHERE d.snapshot_id=$1 GROUP BY a.adapter_key,d.severity ORDER BY a.adapter_key,d.severity LIMIT 384",
                snapshot_id,
            )
        ]
    return {
        "version": 1,
        "days": days,
        "metrics": [dict(row) for row in metrics],
        "coverage": coverage,
    }
