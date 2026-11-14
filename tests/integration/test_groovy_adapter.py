import asyncio
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.groovy_adapter import GroovySourceAdapter
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.source_adapters import AdapterRegistry, index_sources
from code_crawler.ucm import DataAccess, SourceAnalysis, SourceFile, Symbol

pytestmark = pytest.mark.integration


def test_mixed_groovy_java_roundtrip_diagnostics_and_incremental_reuse(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "Groovy Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            for name, text in {
                "A.java": "class A {}",
                "Repo.groovy": 'class Repo { def rows(id) { def q="select id from users"; sql.rows(q) } }',
                "Broken.groovy": "class {",
                "build.gradle": 'println "build"',
            }.items():
                (tmp_path / name).write_text(text)
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="groovy", display_name="groovy", source=str(tmp_path)
                ),
            )
            registry = AdapterRegistry(
                (JavaSourceAdapter(profile="symbols"), GroovySourceAdapter())
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
            assert reports["Broken.groovy"].diagnostics
            assert not reports["Repo.groovy"].diagnostics
            assert reports["build.gradle"].adapter_key == "groovy"
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
            (tmp_path / "Repo.groovy").write_text(
                'class Repo { def rows() { def q="delete from orders" } }'
            )
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "change Groovy", cwd=tmp_path)
            changed = await index_sources(conn, repo, tmp_path, registry)
            assert changed.plan.reanalyze == ("Repo.groovy",)
            await validate_snapshot(conn, changed.snapshot_id)
            updated = await load_snapshot_batch(conn, changed.snapshot_id)
            assert any(
                isinstance(e, DataAccess) and e.access_kind == "DELETE"
                for e in updated.entities
            )
        finally:
            await conn.close()

    asyncio.run(scenario())
