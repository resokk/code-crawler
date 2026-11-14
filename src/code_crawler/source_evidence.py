"""Immutable captured source archives and hash-checked snapshot-scoped evidence."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

import asyncpg

from code_crawler.ucm import SourceRange

if TYPE_CHECKING:
    from code_crawler.incremental import SourceInput


class SourceUnavailableError(ValueError):
    """A historical publication has no archived bytes; integrity failures are different."""


async def archive_sources(
    conn: asyncpg.Connection,
    snapshot_id: UUID,
    sources: tuple[SourceInput, ...],
    *,
    origin: Literal["CAPTURED_WORKTREE", "PROVIDED_BYTES"],
) -> None:
    """Attach exact bytes before validation, atomically with a surrounding ingest transaction."""
    if origin not in ("CAPTURED_WORKTREE", "PROVIDED_BYTES"):
        raise ValueError("invalid source byte origin")

    def records() -> tuple[list[tuple], list[tuple]]:
        if len({s.file.id for s in sources}) != len(sources):
            raise ValueError("duplicate source file archive input")
        blobs = {}
        links = []
        for source in sources:
            if (
                not isinstance(source.content, bytes)
                or hashlib.sha256(source.content).hexdigest()
                != source.file.content_sha256
            ):
                raise ValueError("source bytes do not match content_sha256")
            repo = UUID(source.file.repository_id)
            blobs[(repo, source.file.content_sha256)] = (
                repo,
                source.file.content_sha256,
                source.content,
            )
            links.append(
                (snapshot_id, source.file.id, repo, source.file.content_sha256, origin)
            )
        return list(blobs.values()), links

    blobs, links = await asyncio.to_thread(records)
    async with conn.transaction():
        await conn.executemany(
            "INSERT INTO public.ucm_source_blobs(repository_id,content_sha256,content) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
            blobs,
        )
        await conn.executemany(
            "INSERT INTO public.ucm_snapshot_sources(snapshot_id,source_file_id,repository_id,content_sha256,origin) VALUES ($1,$2,$3,$4,$5)",
            links,
        )


async def evidence_status(conn: asyncpg.Connection, snapshot_id: UUID) -> dict:
    """Report archive completeness without implying historical bytes were retained."""
    row = await conn.fetchrow(
        "SELECT (SELECT count(*) FROM public.ucm_source_files f WHERE f.snapshot_id=s.id) AS source_files, "
        "(SELECT count(*) FROM public.ucm_snapshot_sources a JOIN public.ucm_source_files f "
        "ON (f.snapshot_id,f.entity_id,f.content_sha256)=(a.snapshot_id,a.source_file_id,a.content_sha256) WHERE a.snapshot_id=s.id) AS archived_files, "
        "EXISTS(SELECT 1 FROM public.ucm_source_evidence_legacy_snapshots l WHERE l.snapshot_id=s.id) AS legacy "
        "FROM public.ucm_snapshots s WHERE s.id=$1",
        snapshot_id,
    )
    if row is None:
        raise ValueError("snapshot does not exist")
    status = (
        "ARCHIVED"
        if row["source_files"] == row["archived_files"]
        else "UNAVAILABLE_LEGACY"
        if row["legacy"]
        else "MISSING"
    )
    return {
        "status": status,
        "source_files": row["source_files"],
        "archived_files": row["archived_files"],
    }


async def require_source_archive(conn: asyncpg.Connection, snapshot_id: UUID) -> None:
    """Reject new snapshots whose SourceFiles cannot be restored without a checkout."""
    if (await evidence_status(conn, snapshot_id))["status"] == "MISSING":
        raise ValueError(
            "snapshot requires complete archived source bytes before validation/publication"
        )


@dataclass(frozen=True)
class SourceProvenance:
    repository_id: UUID
    snapshot_id: UUID
    source_file_id: str
    path: str
    content_sha256: str
    origin: str
    commit_hash: str
    source_fingerprint: str
    dirty: bool


@dataclass(frozen=True)
class ArchivedSource:
    provenance: SourceProvenance
    content: bytes


@dataclass(frozen=True)
class SourceFragment:
    provenance: SourceProvenance
    source_range: SourceRange
    content: bytes


async def read_source_file(
    conn: asyncpg.Connection,
    repository_id: UUID,
    snapshot_id: UUID,
    source_file_id: str,
) -> ArchivedSource:
    """Read verified bytes from a published historical snapshot, never mutable filesystem state."""
    row = await conn.fetchrow(
        "SELECT s.repository_id,s.id AS snapshot_id,s.commit_hash,s.source_fingerprint,s.dirty,s.state, "
        "f.entity_id,f.path,f.content_sha256,a.origin,b.content FROM public.ucm_snapshots s "
        "JOIN public.ucm_source_files f ON f.snapshot_id=s.id "
        "LEFT JOIN public.ucm_snapshot_sources a ON a.snapshot_id=f.snapshot_id AND a.source_file_id=f.entity_id AND a.content_sha256=f.content_sha256 "
        "LEFT JOIN public.ucm_source_blobs b ON (b.repository_id,b.content_sha256)=(a.repository_id,a.content_sha256) "
        "WHERE s.repository_id=$1 AND s.id=$2 AND f.entity_id=$3",
        repository_id,
        snapshot_id,
        source_file_id,
    )
    if row is None:
        raise ValueError("source does not belong to the requested repository/snapshot")
    if row["state"] not in ("PUBLISHED", "RETIRED"):
        raise ValueError("source evidence requires a PUBLISHED/RETIRED snapshot")
    if row["content"] is None:
        raise SourceUnavailableError("source bytes unavailable for historical snapshot")
    content = bytes(row["content"])
    digest = await asyncio.to_thread(lambda: hashlib.sha256(content).hexdigest())
    if digest != row["content_sha256"]:
        raise ValueError("archived source content_sha256 mismatch")
    return ArchivedSource(
        SourceProvenance(
            repository_id,
            snapshot_id,
            source_file_id,
            row["path"],
            row["content_sha256"],
            row["origin"],
            row["commit_hash"],
            row["source_fingerprint"],
            row["dirty"],
        ),
        content,
    )


def _slice(content: bytes, location: SourceRange) -> bytes:
    lines = content.split(b"\n")
    offsets = [0]
    for line in lines[:-1]:
        offsets.append(offsets[-1] + len(line) + 1)
    values = []
    for position in (location.start, location.end):
        if position.line > len(lines) or position.byte_column > len(
            lines[position.line - 1]
        ):
            raise ValueError("source range exceeds archived bytes")
        line = lines[position.line - 1]
        try:
            line[: position.byte_column].decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ValueError("source range is not a UTF-8 byte boundary") from error
        values.append(offsets[position.line - 1] + position.byte_column)
    return content[values[0] : values[1]]


async def read_source_fragment(
    conn: asyncpg.Connection,
    repository_id: UUID,
    snapshot_id: UUID,
    location: SourceRange,
) -> SourceFragment:
    """Restore an exclusive UTF-8 byte range with full-file integrity and provenance."""
    source = await read_source_file(
        conn, repository_id, snapshot_id, location.source_file_id
    )
    content = await asyncio.to_thread(_slice, source.content, location)
    return SourceFragment(source.provenance, location, content)
