import asyncio
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.incremental import index_incremental
from code_crawler.java_symbols import analyze_files
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import Occurrence, Symbol

pytestmark = pytest.mark.integration


def test_java_symbols_persist_and_incrementally_reuse_identity(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "Java Symbols Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            (tmp_path / "A.java").write_text(
                "class A { int f; void m(int x) { f=x; } void m(String x) {} }"
            )
            (tmp_path / "B.java").write_text("class B { void work() {} }")
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="java", display_name="java", source=str(tmp_path)
                ),
            )
            first = await index_incremental(
                conn,
                repo,
                tmp_path,
                analyze_files,
                languages={".java": "java"},
                analysis_version="java.symbols/1",
            )
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            original = await load_snapshot_batch(conn, first.snapshot_id)
            methods = {
                e.id
                for e in original.entities
                if isinstance(e, Symbol) and e.name == "m"
            }
            assert len(methods) == 2
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_occurrences WHERE snapshot_id=$1 AND occurrence_kind='WRITE' AND resolution='RESOLVED'",
                    first.snapshot_id,
                )
                == 1
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_evidence WHERE snapshot_id=$1",
                    first.snapshot_id,
                )
                > 0
            )
            (tmp_path / "A.java").write_text(
                "// body edit\nclass A { int f; void m(int x) { int y=x; f=y; } void m(String x) {} }"
            )
            second = await index_incremental(
                conn,
                repo,
                tmp_path,
                analyze_files,
                languages={".java": "java"},
                analysis_version="java.symbols/1",
            )
            assert second.plan.reanalyze == ("A.java",) and second.plan.reused == (
                "B.java",
            )
            await validate_snapshot(conn, second.snapshot_id)
            updated = await load_snapshot_batch(conn, second.snapshot_id)
            assert {
                e.id
                for e in updated.entities
                if isinstance(e, Symbol) and e.name == "m"
            } == methods
            assert any(
                isinstance(e, Symbol) and e.name == "y" for e in updated.entities
            )
            assert any(
                isinstance(e, Occurrence)
                and e.name == "y"
                and e.resolution == "RESOLVED"
                for e in updated.entities
            )
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
            (tmp_path / "A.java").write_text("class A { int f }")
            with pytest.raises(ValueError, match="parser diagnostics"):
                await index_incremental(
                    conn,
                    repo,
                    tmp_path,
                    analyze_files,
                    languages={".java": "java"},
                    analysis_version="java.symbols/1",
                )
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
        finally:
            await conn.close()

    asyncio.run(scenario())
