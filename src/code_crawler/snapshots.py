"""Repository identity, immutable snapshot metadata and publication pointer reads."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import asyncpg
from pydantic import Field

from code_crawler.ucm import ContractModel, Text


class RepositoryInput(ContractModel):
    repository_key: Text
    display_name: Text
    source: Text


class SnapshotInput(ContractModel):
    commit_hash: Text
    branch: Text | None = None
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    dirty: bool


async def register_repository(
    conn: asyncpg.Connection, metadata: RepositoryInput
) -> UUID:
    """Return stable UUID for an explicit repository key without renaming metadata."""
    async with conn.transaction():
        repository_id = await conn.fetchval(
            "INSERT INTO ucm_repositories(id, repository_key, display_name, source) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (repository_key) DO NOTHING RETURNING id",
            uuid4(),
            metadata.repository_key,
            metadata.display_name,
            metadata.source,
        )
        if repository_id is not None:
            return repository_id
        return await conn.fetchval(
            "SELECT id FROM ucm_repositories WHERE repository_key=$1",
            metadata.repository_key,
        )


async def create_snapshot(
    conn: asyncpg.Connection,
    repository_id: UUID,
    metadata: SnapshotInput,
    *,
    snapshot_id: UUID | None = None,
) -> UUID:
    """Create a fresh BUILDING snapshot without changing publication visibility."""
    return await conn.fetchval(
        "INSERT INTO ucm_snapshots "
        "(id, repository_id, commit_hash, branch, source_fingerprint, dirty) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        snapshot_id if snapshot_id is not None else uuid4(),
        repository_id,
        metadata.commit_hash,
        metadata.branch,
        metadata.source_fingerprint,
        metadata.dirty,
    )


async def published_snapshot(
    conn: asyncpg.Connection, repository_id: UUID
) -> asyncpg.Record | None:
    """Read only the snapshot selected by the repository publication pointer."""
    return await conn.fetchrow(
        "SELECT s.* FROM ucm_repository_publications p "
        "JOIN ucm_snapshots s ON (s.repository_id, s.id) = "
        "(p.repository_id, p.snapshot_id) WHERE p.repository_id=$1",
        repository_id,
    )


_SNAPSHOT_LOCK = 4_217_003
_TRY_GC_LEASE = "SELECT pg_try_advisory_xact_lock($1, hashtext($2::text))"


async def pin_snapshot(conn: asyncpg.Connection, snapshot_id: UUID) -> None:
    """Keep a snapshot out of GC until this read transaction ends or disconnects."""
    if not conn.is_in_transaction():
        raise ValueError("snapshot pin requires an active transaction")
    await conn.execute(
        "SELECT pg_advisory_xact_lock_shared($1, hashtext($2::text))",
        _SNAPSHOT_LOCK,
        str(snapshot_id),
    )


@asynccontextmanager
async def pinned_baseline(
    conn: asyncpg.Connection, repository_id: UUID
) -> AsyncIterator[asyncpg.Record | None]:
    """Keep one immutable baseline available without a long-running transaction."""
    if conn.is_in_transaction():
        raise ValueError("baseline lease requires a free connection")
    for _ in range(3):
        baseline = await published_snapshot(conn, repository_id)
        if baseline is None:
            yield None
            return
        key = str(baseline["id"])
        acquired = False
        acquiring = asyncio.create_task(
            conn.fetchval(
                "SELECT pg_try_advisory_lock_shared($1, hashtext($2::text))",
                _SNAPSHOT_LOCK,
                key,
            )
        )
        try:
            try:
                acquired = await asyncio.shield(acquiring)
            except asyncio.CancelledError:
                # Resolve the quick try-lock before releasing exactly our lock count.
                acquired = await acquiring
                raise
            if not acquired:
                continue
            if not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_snapshots WHERE id=$1 AND repository_id=$2 AND state IN ('PUBLISHED','RETIRED'))",
                baseline["id"],
                repository_id,
            ):
                continue
            yield baseline
            return
        finally:
            if acquired and not conn.is_closed():
                await conn.fetchval(
                    "SELECT pg_advisory_unlock_shared($1, hashtext($2::text))",
                    _SNAPSHOT_LOCK,
                    key,
                )
    raise ValueError("baseline changed while acquiring its lease; retry indexing")
