import asyncio
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.incremental import SourceInput
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.kotlin_adapter import KotlinSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.source_adapters import AdapterRegistry, index_sources
from code_crawler.ucm import DataAccess, Relation, SourceAnalysis, SourceFile, Symbol

pytestmark = pytest.mark.integration


def test_kotlin_java_roundtrip_evidence_incremental_and_full_equivalence(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "Kotlin Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            for name, text in {
                "A.java": "public class A { public static int f(int x) { return x; } }",
                "Repo.kt": 'import java.sql.Statement\nfun rows(db: Statement) { val q="select id from users"; db.executeQuery(q); A.f(1) }\n',
                "Broken.kt": "class {",
                "build.kts": "unknown.dynamic()\n",
            }.items():
                (tmp_path / name).write_text(text)
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="kotlin", display_name="kotlin", source=str(tmp_path)
                ),
            )
            registry = AdapterRegistry(
                (JavaSourceAdapter(profile="symbols"), KotlinSourceAdapter())
            )
            first = await index_sources(conn, repo, tmp_path, registry)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            files = {e.id: e.path for e in batch.entities if isinstance(e, SourceFile)}
            reports = {
                files[e.source_file_id]: e
                for e in batch.entities
                if isinstance(e, SourceAnalysis)
            }
            assert reports["Broken.kt"].diagnostics
            assert not reports["Repo.kt"].diagnostics
            assert reports["build.kts"].adapter_key == "kotlin"
            assert any(
                isinstance(e, DataAccess) and e.object_kind == "TABLE"
                for e in batch.entities
            )
            assert any(
                isinstance(e, Symbol) and e.name == "rows" for e in batch.entities
            )
            reused = await index_sources(conn, repo, tmp_path, registry)
            assert not reused.plan.reanalyze
            await validate_snapshot(conn, reused.snapshot_id)
            restored = await load_snapshot_batch(conn, reused.snapshot_id)
            assert {e.id: e for e in batch.entities} == {
                e.id: e for e in restored.entities
            }
            (tmp_path / "Repo.kt").write_text(
                'import java.sql.Statement\nfun rows(db: Statement) { db.executeUpdate("delete from orders") }\n'
            )
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "change Kotlin", cwd=tmp_path)
            changed = await index_sources(conn, repo, tmp_path, registry)
            assert "Repo.kt" in changed.plan.reanalyze
            await validate_snapshot(conn, changed.snapshot_id)
            updated = await load_snapshot_batch(conn, changed.snapshot_id)
            assert any(
                isinstance(e, DataAccess) and e.access_kind == "DELETE"
                for e in updated.entities
            )
            captured = tuple(
                SourceInput(e, (tmp_path / e.path).read_bytes())
                for e in updated.entities
                if isinstance(e, SourceFile)
            )
            full = await registry.prepare(captured)
            full_facts = tuple(e for f in await full(captured) for e in f.entities)
            assert {e.id: e for e in full_facts} == {
                e.id: e for e in updated.entities if not isinstance(e, SourceFile)
            }
            assert any(e.evidence for e in updated.entities if isinstance(e, Relation))
        finally:
            await conn.close()

    asyncio.run(scenario())
