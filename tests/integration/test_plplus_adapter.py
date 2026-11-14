import asyncio
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.groovy_adapter import GroovySourceAdapter
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.plplus_adapter import PlplusSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.source_adapters import AdapterRegistry, index_sources
from code_crawler.ucm import (
    ExternalReference,
    Relation,
    RelationKind,
    SourceAnalysis,
    SourceFile,
)

pytestmark = pytest.mark.integration


def test_plplus_mixed_snapshot_roundtrip_reuse_and_catalog_invalidation(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "PLPlus Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            definition = "C/methods/M/src/private.plp"
            caller = "C/methods/M/src/execute.plp"
            for path, text in {
                "A.java": "class A {}",
                "B.groovy": 'println "ok"',
                definition: "procedure f(p number) is begin null; end;",
                caller: "begin f(1); update x(x.[A]=1) in ::[C] where x.[B]=2; end;",
                "Broken.plp": "begin @; end;",
            }.items():
                file = tmp_path / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(text)
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="plplus", display_name="plplus", source=str(tmp_path)
                ),
            )
            registry = AdapterRegistry(
                (
                    JavaSourceAdapter(profile="symbols"),
                    GroovySourceAdapter(),
                    PlplusSourceAdapter(),
                )
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
            assert {r.adapter_key for r in reports.values()} == {
                "java.symbols",
                "groovy",
                "plplus",
            }
            assert reports["Broken.plp"].diagnostics[0].code.startswith("plplus.")
            assert any(
                isinstance(e, ExternalReference)
                and e.evidence[0].rule == "cft.UPDATE.CLASS"
                for e in batch.entities
            )
            assert any(
                isinstance(e, Relation)
                and e.relation_kind == RelationKind.CALLS
                and e.resolution.status == "PARTIAL"
                for e in batch.entities
            )
            reused = await index_sources(conn, repo, tmp_path, registry)
            assert not reused.plan.reanalyze
            await validate_snapshot(conn, reused.snapshot_id)
            restored = await load_snapshot_batch(conn, reused.snapshot_id)
            assert {e.id: e for e in batch.entities} == {
                e.id: e for e in restored.entities
            }
            (tmp_path / definition).write_text(
                "procedure g(p number) is begin null; end;"
            )
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "rename declaration", cwd=tmp_path)
            changed = await index_sources(conn, repo, tmp_path, registry)
            assert caller in changed.plan.reanalyze
            await validate_snapshot(conn, changed.snapshot_id)
            updated = await load_snapshot_batch(conn, changed.snapshot_id)
            assert not any(
                isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
                for e in updated.entities
            )
            assert any(
                isinstance(e, ExternalReference)
                and e.selector.qualified_name == "plplus.call::f(1)"
                for e in updated.entities
            )
        finally:
            await conn.close()

    asyncio.run(scenario())
