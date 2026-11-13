"""Repository identity and snapshot metadata; publication is a later change."""

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
            "INSERT INTO public.ucm_repositories(id, repository_key, display_name, source) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (repository_key) DO NOTHING RETURNING id",
            uuid4(),
            metadata.repository_key,
            metadata.display_name,
            metadata.source,
        )
        if repository_id is not None:
            return repository_id
        return await conn.fetchval(
            "SELECT id FROM public.ucm_repositories WHERE repository_key=$1",
            metadata.repository_key,
        )


async def create_snapshot(
    conn: asyncpg.Connection, repository_id: UUID, metadata: SnapshotInput
) -> UUID:
    """Create a fresh BUILDING snapshot without changing publication visibility."""
    return await conn.fetchval(
        "INSERT INTO public.ucm_snapshots "
        "(id, repository_id, commit_hash, branch, source_fingerprint, dirty) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        uuid4(),
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
        "SELECT s.* FROM public.ucm_repository_publications p "
        "JOIN public.ucm_snapshots s ON (s.repository_id, s.id) = "
        "(p.repository_id, p.snapshot_id) WHERE p.repository_id=$1",
        repository_id,
    )
