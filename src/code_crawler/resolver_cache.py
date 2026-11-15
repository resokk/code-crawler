"""Disposable PostgreSQL resolver cache; requests read, maintenance alone writes."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import asyncpg
from pydantic import ValidationError

from code_crawler import discovery
from code_crawler.resolver_context import GC_LOCK, ResolverContext, verify_context

if TYPE_CHECKING:
    from code_crawler.external_candidates import CandidateResolution

VERSION = "resolver.cache/1"
CACHE_LOCK = 4_217_004
DEFAULT_TTL = 300
MAX_TTL = 3600
MAX_ENTRIES = 1000
MAX_PAYLOAD_BYTES = 262144
_LOG = logging.getLogger(__name__)
_REFERENCE_FIELDS = frozenset(
    (
        "snapshot_id",
        "entity_id",
        "entity_type",
        "source_id",
        "source_type",
        "certainty",
        "coverage_capability",
        "coverage_analyzer_version",
        "coverage_status",
        "resolution",
        "reason",
    )
)


@dataclass(frozen=True)
class CacheIdentity:
    cache_key: str
    selector_hash: str
    generations_hash: str
    descriptor: dict


@dataclass(frozen=True)
class CacheWarmResult:
    result: CandidateResolution
    stored: bool
    cache_key: str | None
    reason: str
    expires_at: datetime | None = None
    evicted_entries: int = 0


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def event(
    status: str, reason: str, context: ResolverContext, key: str | None = None
) -> None:
    """Emit per-request hit/miss telemetry without source text or mutable worker counters."""
    _LOG.info(
        "resolver_cache",
        extra={
            "cache_status": status,
            "cache_reason": reason,
            "cache_key": key,
            "context_fingerprint": context.fingerprint,
        },
    )


def make_identity(
    descriptor: dict, context: ResolverContext, limit: int, algorithm_version: str
) -> CacheIdentity:
    """Bind selector reuse to exact provenance, versions, algorithm and response bounds."""
    selector_hash = _hash(
        {k: value for k, value in descriptor.items() if k not in _REFERENCE_FIELDS}
    )
    generations_hash = _hash(
        sorted(
            (str(s.repository_id), str(s.snapshot_id), str(s.generation))
            for s in context.selections
        )
    )
    key = _hash(
        [
            VERSION,
            selector_hash,
            _hash(descriptor),
            context.fingerprint,
            generations_hash,
            discovery.VERSION,
            algorithm_version,
            limit,
        ]
    )
    return CacheIdentity(key, selector_hash, generations_hash, descriptor)


async def _identity(conn, source_key, reference_id, context, limit, algorithm_version):
    source = next(s for s in context.selections if s.repository_key == source_key)
    descriptor = await conn.fetchval(
        "SELECT to_jsonb(r)::text FROM public.ucm_external_references r WHERE r.snapshot_id=$1 AND r.entity_id=$2",
        source.snapshot_id,
        reference_id,
    )
    return (
        make_identity(json.loads(descriptor), context, limit, algorithm_version)
        if descriptor
        else None
    )


def _matches(result, identity, context, source_key, limit, algorithm_version):
    source = next(s for s in context.selections if s.repository_key == source_key)
    d = identity.descriptor
    if (
        result.source_repository_id != source.repository_id
        or result.source_snapshot_id != source.snapshot_id
        or result.external_reference_id != d["entity_id"]
        or result.origin.id != d["source_id"]
        or result.origin.entity_type != d["source_type"]
        or result.context_fingerprint != context.fingerprint
        or result.reference_certainty != d["certainty"]
        or result.reference_coverage.status != d["coverage_status"]
        or result.reference_coverage.capability != d["coverage_capability"]
        or result.reference_coverage.analyzer_version != d["coverage_analyzer_version"]
        or result.unavailable_repositories
        or len(result.candidates) > limit
    ):
        return False
    if (
        not result.source_evidence
        or result.coverage.analyzer_version != algorithm_version
    ):
        return False
    if result.status == "RESOLVED":
        if (
            result.reference_certainty != "STATIC_PROVEN"
            or result.reference_coverage.status != "COMPLETE"
            or result.coverage.status != "COMPLETE"
            or any(not e.available for e in result.source_evidence)
            or result.target.certainty != "STATIC_PROVEN"
            or not result.target.evidence.available
            or d["selector_kind"] == "HTTP"
        ):
            return False
        if d["selector_kind"] == "SYMBOL":
            from code_crawler.external_candidates import normalize_selector
            from code_crawler.ucm import SymbolSelector

            types = d["parameter_type_names"]
            if not normalize_selector(
                SymbolSelector(
                    qualified_name=d["qualified_name"],
                    parameter_type_names=tuple(types) if types is not None else None,
                )
            ).complete:
                return False
    elif any(c.certainty != "INFERRED" for c in result.candidates):
        return False
    selections = {s.repository_key: s for s in context.selections}
    for candidate in result.candidates:
        selected = selections.get(candidate.repository_key)
        if not selected or (
            candidate.repository_id,
            candidate.snapshot_id,
            candidate.generation,
        ) != (selected.repository_id, selected.snapshot_id, selected.generation):
            return False
        evidence = candidate.evidence
        if (
            evidence.repository_id,
            evidence.snapshot_id,
            evidence.generation,
            evidence.entity_id,
        ) != (
            candidate.repository_id,
            candidate.snapshot_id,
            candidate.generation,
            candidate.target.id,
        ):
            return False
    return all(
        (e.repository_id, e.snapshot_id, e.generation, e.entity_id)
        == (
            source.repository_id,
            source.snapshot_id,
            source.generation,
            result.external_reference_id,
        )
        for e in result.source_evidence
    )


async def _read_cached_resolution(
    conn: asyncpg.Connection,
    source_key: str,
    reference_id: str,
    context: ResolverContext,
    limit: int,
    algorithm_version: str,
) -> CandidateResolution | None:
    """Read only after the resolver has re-authorized and verified its complete context."""
    from code_crawler.external_candidates import CandidateResolution

    identity = await _identity(
        conn, source_key, reference_id, context, limit, algorithm_version
    )
    if identity is None:
        event("MISS", "SOURCE_NOT_EXTERNAL", context)
        return None
    if not await conn.fetchval("SELECT to_regclass('public.resolver_cache_entries')"):
        event("MISS", "STORAGE_UNAVAILABLE", context, identity.cache_key)
        return None
    try:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT payload,payload_sha256,expires_at>statement_timestamp() AS fresh "
                "FROM public.resolver_cache_entries WHERE cache_key=$1",
                identity.cache_key,
            )
    except asyncpg.UndefinedTableError:
        event("MISS", "STORAGE_UNAVAILABLE", context, identity.cache_key)
        return None
    if row is None or not row["fresh"]:
        event(
            "MISS", "ABSENT" if row is None else "EXPIRED", context, identity.cache_key
        )
        return None
    payload = row["payload"]
    if (
        len(payload.encode()) > MAX_PAYLOAD_BYTES
        or hashlib.sha256(payload.encode()).hexdigest() != row["payload_sha256"]
    ):
        event("MISS", "INVALID_ENTRY", context, identity.cache_key)
        return None
    try:
        result = CandidateResolution.model_validate_json(payload)
    except ValidationError:
        event("MISS", "INVALID_ENTRY", context, identity.cache_key)
        return None
    if not _matches(result, identity, context, source_key, limit, algorithm_version):
        event("MISS", "INVALID_SCOPE", context, identity.cache_key)
        return None
    event("HIT", "FRESH", context, identity.cache_key)
    return result


async def _prune(conn, maximum):
    expired = await conn.fetch(
        "DELETE FROM public.resolver_cache_entries WHERE expires_at<=clock_timestamp() RETURNING cache_key"
    )
    excess = await conn.fetch(
        "DELETE FROM public.resolver_cache_entries WHERE cache_key IN "
        "(SELECT cache_key FROM public.resolver_cache_entries ORDER BY created_at DESC,cache_key DESC OFFSET $1) RETURNING cache_key",
        maximum,
    )
    return len(expired) + len(excess)


async def prune_resolver_cache(conn: asyncpg.Connection) -> int:
    """Remove expired/oldest cache entries without touching canonical facts or pins."""
    if conn.is_in_transaction():
        raise ValueError("cache maintenance requires a free connection")
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", CACHE_LOCK)
        return await _prune(conn, MAX_ENTRIES)


async def warm_resolver_cache(
    conn: asyncpg.Connection,
    source_key: str,
    reference_id: str,
    context: ResolverContext,
    *,
    allowed_repositories: frozenset[str],
    limit: int = 50,
    ttl_seconds: int = DEFAULT_TTL,
) -> CacheWarmResult:
    """Recompute C04, then persist only against the same verified retained generations."""
    from code_crawler import external_candidates

    discovery.authorize(
        tuple(s.repository_key for s in context.selections), allowed_repositories
    )
    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, int)
        or not 1 <= ttl_seconds <= MAX_TTL
    ):
        raise ValueError("cache TTL must be between 1 and 3600 seconds")
    if conn.is_in_transaction():
        raise ValueError("cache warming requires a free connection")
    context = ResolverContext.model_validate_json(context.model_dump_json())
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        result = await external_candidates._resolve_request(
            conn,
            source_key,
            reference_id,
            context,
            allowed_repositories=allowed_repositories,
            limit=limit,
            cache_read=False,
        )
        identity = await _identity(
            conn, source_key, reference_id, context, limit, external_candidates.VERSION
        )
    if result.unavailable_repositories:
        return CacheWarmResult(
            result, False, identity.cache_key, "GENERATION_UNAVAILABLE"
        )
    payload = result.model_dump_json()
    if len(payload.encode()) > MAX_PAYLOAD_BYTES:
        return CacheWarmResult(result, False, identity.cache_key, "OVERSIZED")
    source = next(s for s in context.selections if s.repository_key == source_key)
    try:
        # Locked dependency rows fix provenance; READ COMMITTED sees earlier warmers after the lock wait.
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1)", GC_LOCK)
            await conn.execute("SELECT pg_advisory_xact_lock($1)", CACHE_LOCK)
            await conn.fetch(
                "SELECT id FROM public.ucm_snapshots WHERE id=ANY($1) ORDER BY id FOR KEY SHARE",
                [s.snapshot_id for s in context.selections],
            )
            await conn.fetch(
                "SELECT generation FROM public.search_discovery_generations WHERE generation=ANY($1) ORDER BY generation FOR KEY SHARE",
                [s.generation for s in context.selections],
            )
            if await verify_context(
                conn, context, allowed_repositories=allowed_repositories
            ):
                return CacheWarmResult(
                    result, False, identity.cache_key, "CONTEXT_CHANGED"
                )
            evicted = await _prune(conn, MAX_ENTRIES)
            expires = await conn.fetchval(
                """
                INSERT INTO public.resolver_cache_entries
                (cache_key,source_repository_id,snapshot_id,reference_id,selector_hash,context_fingerprint,
                 generations_hash,algorithm_version,discovery_version,candidate_limit,payload,payload_sha256,expires_at,created_at)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,statement_timestamp()+make_interval(secs=>$13),statement_timestamp())
                ON CONFLICT(cache_key) DO UPDATE SET payload=EXCLUDED.payload,payload_sha256=EXCLUDED.payload_sha256,
                  expires_at=EXCLUDED.expires_at,created_at=EXCLUDED.created_at
                RETURNING expires_at
                """,
                identity.cache_key,
                source.repository_id,
                source.snapshot_id,
                reference_id,
                identity.selector_hash,
                context.fingerprint,
                identity.generations_hash,
                external_candidates.VERSION,
                discovery.VERSION,
                limit,
                payload,
                hashlib.sha256(payload.encode()).hexdigest(),
                ttl_seconds,
            )
            await conn.executemany(
                "INSERT INTO public.resolver_cache_dependencies VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING",
                [
                    (identity.cache_key, s.repository_id, s.snapshot_id, s.generation)
                    for s in context.selections
                ],
            )
            evicted += await _prune(conn, MAX_ENTRIES)
    except (
        asyncpg.SerializationError,
        asyncpg.ForeignKeyViolationError,
        asyncpg.DeadlockDetectedError,
    ):
        return CacheWarmResult(result, False, identity.cache_key, "CONTEXT_CHANGED")
    return CacheWarmResult(result, True, identity.cache_key, "STORED", expires, evicted)
