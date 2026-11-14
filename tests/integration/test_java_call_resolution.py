import asyncio
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.java_calls import index_java
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import ExternalReference, Relation, RelationKind, Symbol

pytestmark = pytest.mark.integration


async def setup(conn: asyncpg.Connection, root: Path, files: dict[str, str]) -> UUID:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Calls Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    for path, text in files.items():
        (root / path).write_text(text)
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="java", display_name="java", source=str(root)
        ),
    )


def test_call_chain_storage_and_dependency_invalidation(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(
                conn,
                tmp_path,
                {
                    "Controller.java": "package p; class Controller { Service service; void handle(){ service.run(); } }",
                    "Service.java": "package p; class Service { Repository repo; void run(){ repo.save(1); } }",
                    "Repository.java": "package p; class Repository { void save(int id){} }",
                    "Unrelated.java": "package p; class Unrelated {}",
                },
            )
            first = await index_java(conn, repo, tmp_path)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            symbols = {e.id: e for e in batch.entities if isinstance(e, Symbol)}
            edges = [
                e
                for e in batch.entities
                if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
            ]
            assert {
                (
                    symbols[e.source.id].qualified_name,
                    symbols[e.resolution.target.id].qualified_name,
                )
                for e in edges
            } == {
                ("p.Controller.handle", "p.Service.run"),
                ("p.Service.run", "p.Repository.save"),
            }
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_evidence WHERE snapshot_id=$1 AND analyzer='java.calls'",
                    first.snapshot_id,
                )
                == 2
            )
            (tmp_path / "Repository.java").write_text(
                "package p; class Repository { void save(int id){ int changed=1; } }"
            )
            second = await index_java(conn, repo, tmp_path)
            assert not second.plan.full_rebuild
            assert second.plan.reanalyze == (
                "Controller.java",
                "Repository.java",
                "Service.java",
            )
            assert second.plan.reused == ("Unrelated.java",)
            await validate_snapshot(conn, second.snapshot_id)
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_new_catalog_type_replaces_external_reference(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(
                conn,
                tmp_path,
                {
                    "A.java": "import ext.Client; class A { Client client; void run(){ client.send(); } }"
                },
            )
            first = await index_java(conn, repo, tmp_path)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            assert any(
                isinstance(e, ExternalReference)
                for e in (await load_snapshot_batch(conn, first.snapshot_id)).entities
            )
            (tmp_path / "Client.java").write_text(
                "package ext; public class Client { public void send(){} }"
            )
            await repos.git("add", "Client.java", cwd=tmp_path)
            second = await index_java(conn, repo, tmp_path)
            assert second.plan.full_rebuild and second.plan.reanalyze == (
                "A.java",
                "Client.java",
            )
            await validate_snapshot(conn, second.snapshot_id)
            batch = await load_snapshot_batch(conn, second.snapshot_id)
            assert not any(isinstance(e, ExternalReference) for e in batch.entities)
            assert all(
                e.resolution.status == "RESOLVED"
                for e in batch.entities
                if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
            )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_ambiguous_partial_and_external_results_survive_storage(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(
                conn,
                tmp_path,
                {
                    "A.java": """class A { ext.Client client;
                void m(int x){} void m(String x){} void one(int x){}
                void run(Object x){ m(x); one(x); client.send(); }
            }"""
                },
            )
            result = await index_java(conn, repo, tmp_path)
            await validate_snapshot(conn, result.snapshot_id)
            batch = await load_snapshot_batch(conn, result.snapshot_id)
            edges = [
                e
                for e in batch.entities
                if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
            ]
            assert {e.resolution.status for e in edges} == {
                "AMBIGUOUS",
                "PARTIAL",
                "UNRESOLVED",
            }
            assert all(e.resolution.target is None for e in edges)
            assert any(
                isinstance(e, ExternalReference)
                and e.selector.qualified_name == "ext.Client.send"
                for e in batch.entities
            )
            from code_crawler.incremental import _capture, index_incremental
            from code_crawler.java_calls import JavaCallAnalyzer

            captured = await _capture(tmp_path, repo, {".java": "java"})
            analyzer = JavaCallAnalyzer(captured.sources)
            with pytest.raises(ValueError, match="catalog profile"):
                await index_incremental(
                    conn,
                    repo,
                    tmp_path,
                    analyzer,
                    languages={".java": "java"},
                    analysis_version="java.calls/1",
                )
        finally:
            await conn.close()

    asyncio.run(scenario())
