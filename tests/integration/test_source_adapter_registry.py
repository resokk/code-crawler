import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.source_adapters import (
    AdapterDescriptor,
    AdapterError,
    AdapterFileResult,
    AdapterRegistry,
    SourceRoute,
    index_sources,
)
from code_crawler.ucm import (
    Coverage,
    EntityType,
    SourceAnalysis,
    SourceFile,
    Symbol,
    logical_id,
)

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class FixtureAdapter:
    key: str
    suffix: str
    version: str = "1"

    @property
    def descriptor(self) -> AdapterDescriptor:
        return AdapterDescriptor(
            key=self.key,
            version=self.version,
            routes=(SourceRoute(suffix=self.suffix, language=self.key),),
            capabilities=(
                Coverage(
                    capability="fixture.symbols",
                    analyzer_version="1",
                    status="COMPLETE",
                ),
            ),
            entity_types=(EntityType.SYMBOL,),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]):
        adapter = self

        class Prepared:
            analysis_version = "fixture/" + adapter.version

            async def __call__(
                self, selected: tuple[SourceInput, ...]
            ) -> tuple[AdapterFileResult, ...]:
                output = []
                for src in selected:
                    key = "fixture:" + src.file.path
                    symbol = Symbol(
                        repository_id=src.file.repository_id,
                        logical_key=key,
                        id=logical_id(src.file.repository_id, EntityType.SYMBOL, key),
                        name=src.file.name,
                        symbol_kind="CLASS",
                        qualified_name=src.file.path,
                    )
                    output.append(
                        AdapterFileResult(
                            analysis=FileAnalysis(
                                path=src.file.path, entities=(symbol,)
                            )
                        )
                    )
                return tuple(output)

        return Prepared()


async def setup(conn: asyncpg.Connection, root: Path) -> UUID:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Registry Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    for path, text in {
        "Broken.java": "class Broken{void m( {",
        "A.tag": "one",
        "A.d.tag": "declaration",
        "README.md": "metadata",
    }.items():
        (root / path).write_text(text)
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="registry", display_name="registry", source=str(root)
        ),
    )


def registry(version: str = "1", profile: str = "symbols") -> AdapterRegistry:
    return AdapterRegistry(
        (
            FixtureAdapter("fixture.base", ".tag", version),
            FixtureAdapter("fixture.declarations", ".d.tag"),
            JavaSourceAdapter(profile=profile),
        )
    )


def test_registry_multi_adapter_routing_report_roundtrip_and_reuse(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            first = await index_sources(conn, repo, tmp_path, registry())
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            reports = [e for e in batch.entities if isinstance(e, SourceAnalysis)]
            assert {r.adapter_key for r in reports} == {
                "fixture.base",
                "fixture.declarations",
                "java.symbols",
            }
            files = {e.id: e for e in batch.entities if isinstance(e, SourceFile)}
            assert {files[r.source_file_id].path: r.adapter_key for r in reports} == {
                "Broken.java": "java.symbols",
                "A.tag": "fixture.base",
                "A.d.tag": "fixture.declarations",
            }
            assert (
                next(e for e in files.values() if e.path == "README.md").language
                == "unknown"
            )
            parser = next(r for r in reports if r.adapter_key == "java.symbols")
            assert parser.diagnostics and all(
                c.status != "COMPLETE" for c in parser.capabilities
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ucm_source_diagnostics WHERE snapshot_id=$1",
                    first.snapshot_id,
                )
            reused = await index_sources(conn, repo, tmp_path, registry())
            assert reused.plan.reanalyze == () and reused.plan.reused == (
                "A.d.tag",
                "A.tag",
                "Broken.java",
            )
            await validate_snapshot(conn, reused.snapshot_id)
            restored = await load_snapshot_batch(conn, reused.snapshot_id)
            assert {e.id: e for e in batch.entities} == {
                e.id: e for e in restored.entities
            }
            changed = await index_sources(conn, repo, tmp_path, registry("2"))
            assert changed.plan.reanalyze == ("A.d.tag", "A.tag", "Broken.java")
            await validate_snapshot(conn, changed.snapshot_id)
            before = await conn.fetchval("SELECT count(*) FROM ucm_snapshots")
            with pytest.raises(AdapterError):
                await index_sources(conn, repo, tmp_path, registry(profile="orm"))
            assert await conn.fetchval("SELECT count(*) FROM ucm_snapshots") == before
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == first.snapshot_id
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_readiness_rejects_complete_coverage_with_error_diagnostic(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            result = await index_sources(conn, repo, tmp_path, registry())
            await conn.execute(
                "DELETE FROM ucm_source_analysis_reasons WHERE snapshot_id=$1 AND capability='java.parser.diagnostics'",
                result.snapshot_id,
            )
            await conn.execute(
                "UPDATE ucm_source_analysis_capabilities SET status='COMPLETE' WHERE snapshot_id=$1 AND capability='java.parser.diagnostics'",
                result.snapshot_id,
            )
            with pytest.raises(ValueError, match="complete source capabilities"):
                await validate_snapshot(conn, result.snapshot_id)
            assert await snapshots.published_snapshot(conn, repo) is None
        finally:
            await conn.close()

    asyncio.run(scenario())
