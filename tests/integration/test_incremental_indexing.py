import asyncio
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.incremental import (
    FileAnalysis,
    IncrementalResult,
    SourceInput,
    index_incremental,
)
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.ucm import (
    EntityType,
    Position,
    SourceRange,
    Symbol,
    TypeRef,
    Value,
    logical_id,
)

pytestmark = pytest.mark.integration


class Analyzer:
    def __init__(self, available: set[str]) -> None:
        self.available = available
        self.calls: list[tuple[str, ...]] = []

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[FileAnalysis, ...]:
        self.calls.append(tuple(source.file.path for source in sources))
        result = []
        for source in sources:
            file, content = source.file, source.content.decode()
            lines = content.splitlines()
            name = lines[0] if lines else "Empty"
            key = "symbol:" + file.path
            refs = [
                line.removeprefix("uses:").strip()
                for line in lines
                if line.startswith("uses:")
            ]
            type_ref = None
            if refs:
                target = (
                    logical_id(
                        file.repository_id, EntityType.SYMBOL, "symbol:" + refs[0]
                    )
                    if refs[0] in self.available
                    else None
                )
                type_ref = TypeRef(
                    name=refs[0],
                    resolution="RESOLVED" if target else "UNRESOLVED",
                    target_symbol_id=target,
                )
            location = SourceRange(
                source_file_id=file.id,
                start=Position(line=1, byte_column=0),
                end=Position(line=1, byte_column=len(name.encode())),
            )
            entities = [
                Symbol(
                    repository_id=file.repository_id,
                    logical_key=key,
                    id=logical_id(file.repository_id, EntityType.SYMBOL, key),
                    name=name,
                    qualified_name=name,
                    symbol_kind="CLASS",
                    source_range=location,
                    type_ref=type_ref,
                )
            ]
            for line in lines:
                if line.startswith("sql:"):
                    key = "sql:" + file.path
                    entities.append(
                        Value(
                            repository_id=file.repository_id,
                            logical_key=key,
                            id=logical_id(file.repository_id, EntityType.VALUE, key),
                            name="sql",
                            value_kind="LITERAL",
                            literal=line.removeprefix("sql:"),
                            source_range=location,
                        )
                    )
            deps = tuple(
                line.removeprefix("depends:").strip()
                for line in lines
                if line.startswith("depends:")
            )
            result.append(
                FileAnalysis(
                    path=file.path, entities=tuple(entities), dependencies=deps
                )
            )
        return tuple(result)


async def setup(conn: asyncpg.Connection, root: Path, files: dict[str, str]) -> UUID:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Incremental Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    for path, content in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content)
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="repo", display_name="app", source=str(root)
        ),
    )


async def build(
    conn: asyncpg.Connection,
    repo: UUID,
    root: Path,
    analyzer: Analyzer,
    version: str = "1",
) -> IncrementalResult:
    return await index_incremental(
        conn,
        repo,
        root,
        analyzer,
        languages={".java": "java"},
        analysis_version=version,
    )


async def publish(
    conn: asyncpg.Connection, repo: UUID, result: IncrementalResult
) -> None:
    await validate_snapshot(conn, result.snapshot_id)
    await publish_snapshot(
        conn, repo, result.snapshot_id, expected_snapshot_id=result.base_snapshot_id
    )


def test_no_change_reuses_facts_without_parser(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path, {"A.java": "A", "B.java": "B"})
            analyzer = Analyzer({"A.java", "B.java"})
            first = await build(conn, repo, tmp_path, analyzer)
            assert first.plan.full_rebuild and first.plan.reanalyze == (
                "A.java",
                "B.java",
            )
            await publish(conn, repo, first)
            second = await build(conn, repo, tmp_path, analyzer)
            assert second.plan.reanalyze == () and second.plan.reused == (
                "A.java",
                "B.java",
            )
            assert len(analyzer.calls) == 1
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
            await validate_snapshot(conn, second.snapshot_id)
            old = await load_snapshot_batch(conn, first.snapshot_id)
            new = await load_snapshot_batch(conn, second.snapshot_id)
            assert {e.id: e for e in old.entities} == {e.id: e for e in new.entities}
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ingest_file_entities WHERE snapshot_id=$1",
                    second.snapshot_id,
                )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_dirty_metadata_invalidates_transitive_dependents_only(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(
                conn,
                tmp_path,
                {
                    "A.java": "A\ndepends:B.java",
                    "B.java": "B\ndepends:config.json",
                    "C.java": "C",
                    "config.json": "old",
                },
            )
            analyzer = Analyzer({"A.java", "B.java", "C.java"})
            old = await build(conn, repo, tmp_path, analyzer)
            await publish(conn, repo, old)
            (tmp_path / "config.json").write_text("new")
            result = await build(conn, repo, tmp_path, analyzer)
            assert result.plan.changed == ("config.json",)
            assert result.plan.reanalyze == ("A.java", "B.java")
            assert result.plan.reused == ("C.java",)
            assert await conn.fetchval(
                "SELECT dirty FROM ucm_snapshots WHERE id=$1", result.snapshot_id
            )
            assert await conn.fetchval(
                "SELECT commit_hash FROM ucm_snapshots WHERE id=$1", old.snapshot_id
            ) == await conn.fetchval(
                "SELECT commit_hash FROM ucm_snapshots WHERE id=$1", result.snapshot_id
            )
            await publish(conn, repo, result)
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_structural_dependencies_delete_add_rename_and_sql_stability(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(
                conn,
                tmp_path,
                {
                    "A.java": "A\nuses:B.java\nsql:select * from users",
                    "B.java": "B",
                    "C.java": "C",
                },
            )
            analyzer = Analyzer({"A.java", "B.java", "C.java"})
            old = await build(conn, repo, tmp_path, analyzer)
            await publish(conn, repo, old)
            (tmp_path / "B.java").write_text("B2")
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "change B", cwd=tmp_path)
            updated = await build(conn, repo, tmp_path, analyzer)
            assert updated.plan.reanalyze == (
                "A.java",
                "B.java",
            ) and updated.plan.git_changed == ("B.java",)
            await publish(conn, repo, updated)
            await repos.git("mv", "B.java", "Renamed.java", cwd=tmp_path)
            analyzer.available = {"A.java", "Renamed.java", "C.java"}
            renamed = await build(conn, repo, tmp_path, analyzer)
            assert renamed.plan.deleted == ("B.java",) and renamed.plan.added == (
                "Renamed.java",
            )
            assert renamed.plan.reanalyze == ("A.java", "Renamed.java")
            await publish(conn, repo, renamed)
            original = await load_snapshot_batch(conn, old.snapshot_id)
            current = await load_snapshot_batch(conn, renamed.snapshot_id)
            assert next(e for e in original.entities if isinstance(e, Value)) == next(
                e for e in current.entities if isinstance(e, Value)
            )
            assert logical_id(str(repo), EntityType.SYMBOL, "symbol:B.java") not in {
                e.id for e in current.entities
            }
            assert logical_id(str(repo), EntityType.SYMBOL, "symbol:Renamed.java") in {
                e.id for e in current.entities
            }
            assert any(
                isinstance(e, Symbol)
                and e.type_ref is not None
                and e.type_ref.resolution == "UNRESOLVED"
                for e in current.entities
            )
            full = await build(conn, repo, tmp_path, analyzer, version="force-full")
            await validate_snapshot(conn, full.snapshot_id)
            rebuilt = await load_snapshot_batch(conn, full.snapshot_id)
            assert {e.id: e for e in current.entities} == {
                e.id: e for e in rebuilt.entities
            }

        finally:
            await conn.close()

    asyncio.run(scenario())


def test_profile_change_negative_dependency_and_legacy_baseline(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(
                conn, tmp_path, {"A.java": "A\ndepends:missing.json", "B.java": "B"}
            )
            legacy = await snapshots.create_snapshot(
                conn,
                repo,
                snapshots.SnapshotInput(
                    commit_hash="unavailable", source_fingerprint="a" * 64, dirty=False
                ),
            )
            await validate_snapshot(conn, legacy)
            await publish_snapshot(conn, repo, legacy, expected_snapshot_id=None)
            analyzer = Analyzer({"A.java", "B.java"})
            first = await build(conn, repo, tmp_path, analyzer)
            assert first.plan.full_rebuild
            await publish(conn, repo, first)
            (tmp_path / "missing.json").write_text("new config")
            await repos.git("add", "missing.json", cwd=tmp_path)
            added = await build(conn, repo, tmp_path, analyzer)
            assert added.plan.reanalyze == ("A.java",)
            await publish(conn, repo, added)
            versioned = await build(conn, repo, tmp_path, analyzer, version="2")
            assert versioned.plan.full_rebuild and versioned.plan.reanalyze == (
                "A.java",
                "B.java",
            )
            await publish(conn, repo, versioned)
        finally:
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure", ["parser", "worktree", "missing_result", "manifest_copy"]
)
def test_failed_incremental_build_preserves_publication(
    database_url: str, tmp_path: Path, failure: str
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path, {"A.java": "A"})
            analyzer = Analyzer({"A.java"})
            old = await build(conn, repo, tmp_path, analyzer)
            await publish(conn, repo, old)
            (tmp_path / "A.java").write_text("Changed")

            async def failing(
                sources: tuple[SourceInput, ...],
            ) -> tuple[FileAnalysis, ...]:
                if failure == "parser":
                    raise RuntimeError("parser failure")
                if failure == "worktree":
                    (tmp_path / "A.java").write_text("Changed again")
                if failure == "missing_result":
                    return ()
                return await analyzer(sources)

            if failure == "manifest_copy":
                await conn.execute("""CREATE FUNCTION fail_manifest() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN RAISE EXCEPTION 'manifest failure' USING ERRCODE='23514'; END; $$;
                    CREATE TRIGGER fail_manifest BEFORE INSERT ON ingest_file_entities FOR EACH ROW EXECUTE FUNCTION fail_manifest();""")
            with pytest.raises((ValueError, RuntimeError, asyncpg.CheckViolationError)):
                await index_incremental(
                    conn,
                    repo,
                    tmp_path,
                    failing,
                    languages={".java": "java"},
                    analysis_version="1",
                )
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == old.snapshot_id
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_entities WHERE snapshot_id<>$1",
                    old.snapshot_id,
                )
                == 0
            )
            assert (
                await conn.fetchval("SELECT count(*) FROM ingest_snapshot_profiles")
                == 1
            )
        finally:
            await conn.close()

    asyncio.run(scenario())
