"""Explicit immutable version selections, deployment maps and retained snapshot pins."""

import hashlib
import json
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

import asyncpg
from pydantic import Field, model_validator

from code_crawler.discovery import VERSION as CATALOG_VERSION
from code_crawler.discovery import authorize
from code_crawler.ucm import ContractModel, Text

GC_LOCK = 4_217_003
Mode = Literal["LATEST_INDEXED", "PINNED_SNAPSHOTS", "DEPLOYMENT_CONTEXT"]


class SnapshotPin(ContractModel):
    repository_key: Text
    snapshot_id: UUID


class DeploymentBinding(SnapshotPin):
    service_key: Text


class Selection(SnapshotPin):
    repository_id: UUID
    generation: UUID | None
    commit_hash: Text
    services: tuple[Text, ...] = ()


class ResolverContext(ContractModel):
    contract_version: Literal[1] = 1
    mode: Mode
    deployment_key: Text | None = None
    selections: tuple[Selection, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def consistent(self) -> "ResolverContext":
        if len({s.repository_key for s in self.selections}) != len(self.selections):
            raise ValueError("one snapshot per repository is required")
        if len({s.repository_id for s in self.selections}) != len(self.selections):
            raise ValueError("duplicate repository identity")
        if (self.mode == "DEPLOYMENT_CONTEXT") != (self.deployment_key is not None):
            raise ValueError(
                "deployment mode requires exactly one explicit deployment key"
            )
        if self.mode != "DEPLOYMENT_CONTEXT" and any(
            s.services for s in self.selections
        ):
            raise ValueError("service bindings require an explicit deployment context")
        return self

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        payload["selections"].sort(key=lambda s: s["repository_key"])
        for s in payload["selections"]:
            s["services"].sort()
        return hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()


async def _select(
    conn: asyncpg.Connection,
    mode: Mode,
    repository_keys: tuple[str, ...],
    pins: tuple[SnapshotPin, ...],
    deployment_key: str | None,
) -> ResolverContext:
    if mode not in ("LATEST_INDEXED", "PINNED_SNAPSHOTS", "DEPLOYMENT_CONTEXT"):
        raise ValueError("invalid resolver context mode")
    pin_map = {p.repository_key: p.snapshot_id for p in pins}
    if mode == "PINNED_SNAPSHOTS":
        if (
            len(pin_map) != len(pins)
            or set(pin_map) != set(repository_keys)
            or deployment_key is not None
        ):
            raise ValueError("pins must cover exactly the requested repositories")
    elif pins or (mode == "LATEST_INDEXED" and deployment_key is not None):
        raise ValueError("mode arguments conflict")
    services = {}
    if mode == "DEPLOYMENT_CONTEXT":
        if not deployment_key or not deployment_key.strip():
            raise ValueError("deployment key is required")
        bindings = await conn.fetch(
            "SELECT r.repository_key,b.selected_snapshot_id,b.service_key FROM resolver_deployment_bindings b "
            "JOIN ucm_repositories r ON r.id=b.repository_id "
            "WHERE b.deployment_key=$1 AND r.repository_key=ANY($2)",
            deployment_key,
            list(repository_keys),
        )
        for b in bindings:
            old = pin_map.setdefault(b["repository_key"], b["selected_snapshot_id"])
            if old != b["selected_snapshot_id"]:
                raise ValueError(
                    "deployment selects incompatible versions of one repository"
                )
            services.setdefault(b["repository_key"], []).append(b["service_key"])
        if set(pin_map) != set(repository_keys):
            raise ValueError(
                "unknown or incomplete deployment mapping; latest fallback is forbidden"
            )
    rows = await conn.fetch(
        "SELECT r.repository_key,r.id AS repository_id,s.id AS snapshot_id,s.commit_hash,g.generation "
        "FROM ucm_repositories r JOIN ucm_snapshots s ON s.repository_id=r.id "
        "LEFT JOIN ucm_repository_publications p ON p.repository_id=r.id AND p.snapshot_id=s.id "
        "LEFT JOIN search_discovery_generations g ON g.snapshot_id=s.id AND g.projector_version=$4 AND g.state='READY' "
        "WHERE r.repository_key=ANY($1) AND s.state IN ('PUBLISHED','RETIRED') "
        "AND (($2 AND p.snapshot_id IS NOT NULL) OR (NOT $2 AND s.id=ANY($3::uuid[]))) "
        "ORDER BY r.repository_key",
        list(repository_keys),
        mode == "LATEST_INDEXED",
        list(pin_map.values()),
        CATALOG_VERSION,
    )
    selections = []
    for row in rows:
        if (
            mode != "LATEST_INDEXED"
            and pin_map[row["repository_key"]] != row["snapshot_id"]
        ):
            continue
        selections.append(
            Selection(
                **dict(row),
                services=tuple(sorted(services.get(row["repository_key"], ()))),
            )
        )
    if {s.repository_key for s in selections} != set(repository_keys):
        raise ValueError(
            "snapshot missing, not published/retained, or belongs to another repository"
        )
    return ResolverContext(
        mode=mode, deployment_key=deployment_key, selections=tuple(selections)
    )


async def select_context(
    conn: asyncpg.Connection,
    mode: Mode,
    repository_keys: tuple[str, ...],
    *,
    allowed_repositories: frozenset[str],
    pins: tuple[SnapshotPin, ...] = (),
    deployment_key: str | None = None,
) -> ResolverContext:
    """Freeze a coherent query-time selection; latest selection is recomputed on each call."""
    authorize(repository_keys, allowed_repositories)
    if conn.is_in_transaction():
        if await conn.fetchval("SHOW transaction_isolation") not in (
            "repeatable read",
            "serializable",
        ):
            raise ValueError("context selection requires repeatable read")
        return await _select(conn, mode, repository_keys, pins, deployment_key)
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        return await _select(conn, mode, repository_keys, pins, deployment_key)


async def verify_context(
    conn: asyncpg.Connection,
    context: ResolverContext,
    *,
    allowed_repositories: frozenset[str],
) -> tuple[str, ...]:
    """Check ownership/retention and return unavailable or superseded catalog generations."""
    context = ResolverContext.model_validate_json(context.model_dump_json())
    keys = tuple(s.repository_key for s in context.selections)
    authorize(keys, allowed_repositories)
    fresh = await _select(
        conn,
        "PINNED_SNAPSHOTS",
        keys,
        tuple(
            SnapshotPin(repository_key=s.repository_key, snapshot_id=s.snapshot_id)
            for s in context.selections
        ),
        None,
    )
    by_key = {s.repository_key: s for s in fresh.selections}
    if context.mode == "DEPLOYMENT_CONTEXT":
        deployed = await _select(
            conn, "DEPLOYMENT_CONTEXT", keys, (), context.deployment_key
        )
        expected = {
            s.repository_key: (s.snapshot_id, s.services) for s in deployed.selections
        }
        if any(
            expected[s.repository_key] != (s.snapshot_id, s.services)
            for s in context.selections
        ):
            raise ValueError("deployment mapping identity mismatch")
    unavailable = []
    for selection in context.selections:
        current = by_key[selection.repository_key]
        if (current.repository_id, current.commit_hash) != (
            selection.repository_id,
            selection.commit_hash,
        ):
            raise ValueError("resolver context identity mismatch")
        if selection.generation is None or selection.generation != current.generation:
            unavailable.append(selection.repository_key)
    return tuple(sorted(unavailable))


async def save_context(
    conn: asyncpg.Connection,
    context: ResolverContext,
    *,
    allowed_repositories: frozenset[str],
) -> UUID:
    """Persist an immutable manifest and pin its snapshots until explicit release."""
    authorize(tuple(s.repository_key for s in context.selections), allowed_repositories)
    if conn.is_in_transaction():
        raise ValueError("saving context requires a free connection")
    async with conn.transaction(isolation="repeatable_read"):
        await conn.execute("SELECT pg_advisory_xact_lock($1)", GC_LOCK)
        await verify_context(conn, context, allowed_repositories=allowed_repositories)
        context_id = uuid5(NAMESPACE_URL, "resolver.context/1:" + context.fingerprint)
        inserted = await conn.fetchval(
            "INSERT INTO resolver_contexts VALUES($1,$2,$3::jsonb) ON CONFLICT(id) DO NOTHING RETURNING id",
            context_id,
            context.fingerprint,
            context.model_dump_json(),
        )
        if inserted:
            await conn.executemany(
                "INSERT INTO resolver_context_selections VALUES($1,$2,$3)",
                [
                    (context_id, s.repository_id, s.snapshot_id)
                    for s in context.selections
                ],
            )
        elif (
            await conn.fetchval(
                "SELECT fingerprint FROM resolver_contexts WHERE id=$1",
                context_id,
            )
            != context.fingerprint
        ):
            raise ValueError("context identity collision")
        return context_id


async def load_context(
    conn: asyncpg.Connection, context_id: UUID, *, allowed_repositories: frozenset[str]
) -> ResolverContext:
    """Load a saved selection, rechecking current grants and manifest integrity."""
    if not allowed_repositories:
        raise PermissionError("repository access denied")
    row = await conn.fetchrow(
        "SELECT manifest,fingerprint FROM resolver_contexts WHERE id=$1",
        context_id,
    )
    if row is None:
        raise ValueError("resolver context does not exist")
    context = ResolverContext.model_validate_json(row["manifest"])
    authorize(tuple(s.repository_key for s in context.selections), allowed_repositories)
    if context.fingerprint != row["fingerprint"]:
        raise ValueError("resolver manifest integrity failure")
    return context


async def release_context(
    conn: asyncpg.Connection, context_id: UUID, *, allowed_repositories: frozenset[str]
) -> None:
    """Release a saved context's retention pins without modifying source snapshots."""
    if conn.is_in_transaction():
        raise ValueError("release requires a free connection")
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", GC_LOCK)
        await load_context(conn, context_id, allowed_repositories=allowed_repositories)
        await conn.execute("DELETE FROM resolver_contexts WHERE id=$1", context_id)


async def register_deployment(
    conn: asyncpg.Connection,
    deployment_key: str,
    bindings: tuple[DeploymentBinding, ...],
    *,
    allowed_repositories: frozenset[str],
) -> None:
    """Register an immutable service/deploy mapping; changing versions requires a new key."""
    keys = tuple(sorted({b.repository_key for b in bindings}))
    authorize(keys, allowed_repositories)
    if (
        not deployment_key
        or not deployment_key.strip()
        or len({b.service_key for b in bindings}) != len(bindings)
        or len(bindings) > 32
    ):
        raise ValueError("invalid deployment mapping")
    pins = {b.repository_key: b.snapshot_id for b in bindings}
    if any(pins[b.repository_key] != b.snapshot_id for b in bindings):
        raise ValueError("deployment selects incompatible versions")
    if conn.is_in_transaction():
        raise ValueError("deployment registration requires a free connection")
    async with conn.transaction(isolation="repeatable_read"):
        await conn.execute("SELECT pg_advisory_xact_lock($1)", GC_LOCK)
        context = await _select(
            conn,
            "PINNED_SNAPSHOTS",
            keys,
            tuple(
                SnapshotPin(repository_key=k, snapshot_id=v) for k, v in pins.items()
            ),
            None,
        )
        by_key = {s.repository_key: s for s in context.selections}
        fingerprint = hashlib.sha256(
            json.dumps(
                sorted(
                    (b.service_key, b.repository_key, str(b.snapshot_id))
                    for b in bindings
                )
            ).encode()
        ).hexdigest()
        existing = await conn.fetchval(
            "SELECT fingerprint FROM resolver_deployments WHERE deployment_key=$1",
            deployment_key,
        )
        if existing:
            if existing != fingerprint:
                raise ValueError("deployment mapping is immutable")
            return
        await conn.execute(
            "INSERT INTO resolver_deployments VALUES($1,$2)",
            deployment_key,
            fingerprint,
        )
        await conn.executemany(
            "INSERT INTO resolver_deployment_bindings VALUES($1,$2,$3,$4)",
            [
                (
                    deployment_key,
                    b.service_key,
                    by_key[b.repository_key].repository_id,
                    b.snapshot_id,
                )
                for b in bindings
            ],
        )


async def release_deployment(
    conn: asyncpg.Connection,
    deployment_key: str,
    *,
    allowed_repositories: frozenset[str],
) -> None:
    """Remove an obsolete deployment map and its retention pins after authorization."""
    if conn.is_in_transaction():
        raise ValueError("deployment release requires a free connection")
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", GC_LOCK)
        rows = await conn.fetch(
            "SELECT DISTINCT r.repository_key FROM resolver_deployment_bindings b JOIN ucm_repositories r ON r.id=b.repository_id WHERE b.deployment_key=$1",
            deployment_key,
        )
        authorize(tuple(r["repository_key"] for r in rows), allowed_repositories)
        await conn.execute(
            "DELETE FROM resolver_deployments WHERE deployment_key=$1",
            deployment_key,
        )
