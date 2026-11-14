import asyncio
import hashlib
import shutil
from uuid import uuid4

import asyncpg
import pytest

from code_crawler import db, incremental, repos, snapshots
from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch, ingest_batch
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.publication import (
    publish_snapshot,
    rollback_publication,
    validate_snapshot,
)
from code_crawler.source_adapters import AdapterRegistry, index_sources
from code_crawler.source_evidence import (
    archive_sources,
    evidence_status,
    read_source_file,
    read_source_fragment,
)
from code_crawler.ucm import EntityType, Relation, RelationKind, SourceFile, logical_id

pytestmark = pytest.mark.integration


async def initialize(conn, *, through=None):
    for name in await db.begin_migration(conn, init=True):
        if through is None or name <= through:
            await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="sources", display_name="sources", source="fixture"
        ),
    )


async def source_repo(root):
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Evidence Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    (root / "A.java").write_bytes(
        b"class A { void helper() {} void run(){ helper(); } }\n"
    )
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)


def registry():
    return AdapterRegistry((JavaSourceAdapter(profile="calls"),))


def file(repo, content):
    return SourceFile(
        repository_id=str(repo),
        logical_key="A.java",
        id=logical_id(str(repo), EntityType.SOURCE_FILE, "A.java"),
        name="A.java",
        path="A.java",
        language="java",
        content_sha256=hashlib.sha256(content).hexdigest(),
    )


async def new_snapshot(conn, repo, dirty=False):
    return await snapshots.create_snapshot(
        conn,
        repo,
        snapshots.SnapshotInput(
            commit_hash="head", source_fingerprint="a" * 64, dirty=dirty
        ),
    )


def test_dirty_and_clean_evidence_survives_checkout_deletion_and_reuse(
    database_url, tmp_path
):
    async def run():
        conn = await asyncpg.connect(database_url)
        root = tmp_path / "checkout"
        root.mkdir()
        try:
            repo = await initialize(conn)
            await source_repo(root)
            clean = await index_sources(conn, repo, root, registry())
            await validate_snapshot(conn, clean.snapshot_id)
            await publish_snapshot(
                conn, repo, clean.snapshot_id, expected_snapshot_id=None
            )
            again = await index_sources(conn, repo, root, registry())
            assert not again.plan.reanalyze
            await validate_snapshot(conn, again.snapshot_id)
            await publish_snapshot(
                conn, repo, again.snapshot_id, expected_snapshot_id=clean.snapshot_id
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_source_blobs WHERE repository_id=$1", repo
                )
                == 1
            )
            dirty = '// я\r\nclass A { void helper() {} void run(){ String s="β"; helper(); } }\r\n'.encode()
            (root / "A.java").write_bytes(dirty)
            changed = await index_sources(conn, repo, root, registry())
            await validate_snapshot(conn, changed.snapshot_id)
            await publish_snapshot(
                conn, repo, changed.snapshot_id, expected_snapshot_id=again.snapshot_id
            )
            from code_crawler.publication import load_snapshot_batch

            batch = await load_snapshot_batch(conn, changed.snapshot_id)
            relation = next(
                e
                for e in batch.entities
                if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
            )
            loc = relation.evidence[0].source_range
            await asyncio.to_thread(shutil.rmtree, root)
            fragment = await read_source_fragment(conn, repo, changed.snapshot_id, loc)
            assert fragment.content == b"helper()"
            assert fragment.provenance.dirty
            assert (
                fragment.provenance.content_sha256 == hashlib.sha256(dirty).hexdigest()
            )
            assert fragment.provenance.origin == "CAPTURED_WORKTREE"
            assert (
                fragment.provenance.source_fingerprint
                == (await snapshots.published_snapshot(conn, repo))[
                    "source_fingerprint"
                ]
            )
            restored = await read_source_file(
                conn, repo, changed.snapshot_id, loc.source_file_id
            )
            assert restored.content == dirty
            old = await read_source_file(
                conn, repo, clean.snapshot_id, loc.source_file_id
            )
            assert not old.provenance.dirty and old.content != dirty
            assert (await evidence_status(conn, changed.snapshot_id))[
                "status"
            ] == "ARCHIVED"
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_source_blobs WHERE repository_id=$1", repo
                )
                == 2
            )
            with pytest.raises(ValueError, match="repository/snapshot"):
                await read_source_fragment(conn, uuid4(), changed.snapshot_id, loc)
        finally:
            await conn.close()

    asyncio.run(run())


def test_missing_archive_hash_checks_scoping_and_immutability(database_url):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await initialize(conn)
            content = b"class A {}\n"
            src = file(repo, content)
            snap = await new_snapshot(conn, repo, True)
            await ingest_batch(
                conn, snap, UcmBatch(repository_id=repo, entities=(src,))
            )
            with pytest.raises(ValueError, match="archived source bytes"):
                await validate_snapshot(conn, snap)
            assert (
                await conn.fetchval("SELECT state FROM ucm_snapshots WHERE id=$1", snap)
                == "BUILDING"
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO ucm_source_blobs VALUES ($1,$2,$3)",
                    repo,
                    "a" * 64,
                    content,
                )
            with pytest.raises(asyncpg.CheckViolationError, match="SourceFile hash"):
                await archive_sources(
                    conn,
                    snap,
                    (SourceInput(file(repo, b"different"), b"different"),),
                    origin="PROVIDED_BYTES",
                )
            assert await conn.fetchval("SELECT count(*) FROM ucm_source_blobs") == 0
            await archive_sources(
                conn, snap, (SourceInput(src, content),), origin="PROVIDED_BYTES"
            )
            with pytest.raises(ValueError, match="PUBLISHED/RETIRED"):
                await read_source_file(conn, repo, snap, src.id)
            await validate_snapshot(conn, snap)
            await publish_snapshot(conn, repo, snap, expected_snapshot_id=None)
            for statement, args in (
                ("UPDATE ucm_source_blobs SET content=content", ()),
                ("DELETE FROM ucm_source_blobs", ()),
                ("UPDATE ucm_snapshot_sources SET origin=origin", ()),
                ("DELETE FROM ucm_snapshot_sources", ()),
                ("TRUNCATE ucm_source_blobs CASCADE", ()),
                (
                    "INSERT INTO ucm_source_evidence_legacy_snapshots VALUES ($1)",
                    (snap,),
                ),
            ):
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(statement, *args)

            class CorruptRead:
                async def fetchrow(self, *args):
                    row = dict(await conn.fetchrow(*args))
                    row["content"] = b"corrupted"
                    return row

            with pytest.raises(ValueError, match="content_sha256 mismatch"):
                await read_source_file(CorruptRead(), repo, snap, src.id)
            other = await new_snapshot(conn, repo)
            await ingest_batch(
                conn, other, UcmBatch(repository_id=repo, entities=(src,))
            )
            await conn.execute(
                "UPDATE ucm_snapshots SET state='VALIDATING' WHERE id=$1", other
            )
            await conn.execute(
                "INSERT INTO ucm_snapshot_validations(snapshot_id,entity_count) VALUES ($1,1)",
                other,
            )
            with pytest.raises(
                asyncpg.CheckViolationError, match="archived source bytes"
            ):
                await conn.execute(
                    "UPDATE ucm_snapshots SET state='READY' WHERE id=$1", other
                )
            assert (await snapshots.published_snapshot(conn, repo))["id"] == snap
        finally:
            await conn.close()

    asyncio.run(run())


def test_archive_failure_rolls_back_facts_links_and_new_blobs(
    database_url, tmp_path, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await initialize(conn)
            await source_repo(tmp_path)
            first = await index_sources(conn, repo, tmp_path, registry())
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            original = incremental.archive_sources

            async def failure(*args, **kwargs):
                await original(*args, **kwargs)
                raise ValueError("injected archive failure")

            monkeypatch.setattr(incremental, "archive_sources", failure)
            (tmp_path / "A.java").write_text("class A { void changed() {} }")
            with pytest.raises(ValueError, match="injected archive failure"):
                await index_sources(conn, repo, tmp_path, registry())
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
            assert await conn.fetchval("SELECT count(*) FROM ucm_source_blobs") == 1
            assert await conn.fetchval("SELECT count(*) FROM ucm_snapshot_sources") == 1
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_entities WHERE snapshot_id<>$1)",
                first.snapshot_id,
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_upgrade_keeps_historical_publication_and_explicit_unavailability(database_url):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await initialize(conn, through="0014_source_adapter_registry.sql")
            src = file(repo, b"class A {}")
            old = await new_snapshot(conn, repo, True)
            await ingest_batch(conn, old, UcmBatch(repository_id=repo, entities=(src,)))
            async with conn.transaction():
                await conn.execute(
                    "UPDATE ucm_snapshots SET state='VALIDATING' WHERE id=$1", old
                )
                await conn.execute(
                    "INSERT INTO ucm_snapshot_validations(snapshot_id,entity_count) VALUES ($1,1)",
                    old,
                )
                await conn.execute(
                    "UPDATE ucm_snapshots SET state='READY' WHERE id=$1", old
                )
                await conn.execute(
                    "UPDATE ucm_snapshots SET state='PUBLISHED' WHERE id=$1", old
                )
                await conn.execute(
                    "INSERT INTO ucm_repository_publications(repository_id,snapshot_id) VALUES ($1,$2)",
                    repo,
                    old,
                )
            for name in await db.begin_migration(conn):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            assert (await evidence_status(conn, old))["status"] == "UNAVAILABLE_LEGACY"
            with pytest.raises(ValueError, match="unavailable"):
                await read_source_file(conn, repo, old, src.id)
            new = await new_snapshot(conn, repo)
            await validate_snapshot(conn, new)
            await publish_snapshot(conn, repo, new, expected_snapshot_id=old)
            await rollback_publication(conn, repo, old, expected_snapshot_id=new)
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_source_evidence_legacy_snapshots WHERE snapshot_id=$1)",
                new,
            )
            from code_crawler.jobs import collect_garbage

            latest = await new_snapshot(conn, repo)
            await validate_snapshot(conn, latest)
            await publish_snapshot(conn, repo, latest, expected_snapshot_id=old)
            collected = await collect_garbage(conn, keep_retired=0)
            assert old in collected["retired"]
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_source_evidence_legacy_snapshots WHERE snapshot_id=$1)",
                old,
            )
            assert (await snapshots.published_snapshot(conn, repo))["id"] == latest

        finally:
            await conn.close()

    asyncio.run(run())
