import asyncio
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.incremental import _capture, index_incremental
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.javascript_adapter import (
    JavaScriptSourceAdapter,
    TypeScriptSourceAdapter,
)
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
    Symbol,
)

pytestmark = pytest.mark.integration


def test_js_ts_publication_incremental_config_and_fingerprint(
    database_url: str, tmp_path: Path, monkeypatch
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "D11 Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            for path, text in {
                "A.java": "class A {}",
                "client.js": "export function helper() {} fetch(`/users/${id}`); import(path);",
                "tsconfig.json": '{"compilerOptions":{"paths":{"@api":["./api"]}}}',
                "api.ts": "export function get(x: string): string; export function get(x: number): number; export function get<T>(x: T): T { return x; }",
                "other.ts": "export function get() {}",
                "app.tsx": 'import {get} from "@api"; import {helper} from "./client"; export function App() { get("x"); helper(); return <p/>; }',
                "types.ts": 'import type {get} from "./api"; function run() {get(1);}',
            }.items():
                (tmp_path / path).write_text(text)
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="d11", display_name="d11", source=str(tmp_path)
                ),
            )
            registry = AdapterRegistry(
                (
                    JavaSourceAdapter(profile="symbols"),
                    JavaScriptSourceAdapter(),
                    TypeScriptSourceAdapter(),
                )
            )
            first = await index_sources(conn, repo, tmp_path, registry)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            initial = await load_snapshot_batch(conn, first.snapshot_id)
            assert {
                e.adapter_key for e in initial.entities if isinstance(e, SourceAnalysis)
            } == {"java.symbols", "javascript", "typescript"}
            assert any(
                isinstance(e, ExternalReference)
                and e.selector.kind == "HTTP"
                and e.selector.path == "/users/{dynamic}"
                and e.evidence
                for e in initial.entities
            )
            calls = [
                e
                for e in initial.entities
                if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
            ]
            assert sorted(e.resolution.status for e in calls) == [
                "RESOLVED",
                "RESOLVED",
                "UNRESOLVED",
            ]
            reused = await index_sources(conn, repo, tmp_path, registry)
            assert not reused.plan.reanalyze
            await validate_snapshot(conn, reused.snapshot_id)
            assert {e.id: e for e in initial.entities} == {
                e.id: e
                for e in (await load_snapshot_batch(conn, reused.snapshot_id)).entities
            }
            (tmp_path / "tsconfig.json").write_text(
                '{"compilerOptions":{"paths":{"@api":["./other"]}}}'
            )
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "change config", cwd=tmp_path)
            changed = await index_sources(conn, repo, tmp_path, registry)
            assert "app.tsx" in changed.plan.reanalyze
            await validate_snapshot(conn, changed.snapshot_id)
            updated = await load_snapshot_batch(conn, changed.snapshot_id)
            get = next(
                e
                for e in updated.entities
                if isinstance(e, Symbol) and e.qualified_name == "other.ts::get"
            )
            assert any(
                isinstance(e, Relation)
                and e.relation_kind == RelationKind.CALLS
                and e.resolution.target
                and e.resolution.target.id == get.id
                for e in updated.entities
            )
            await publish_snapshot(
                conn, repo, changed.snapshot_id, expected_snapshot_id=first.snapshot_id
            )
            captured = await _capture(tmp_path, repo, registry.languages)
            prepared = await registry.prepare(captured.sources)

            async def full_analyzer(sources):
                return await prepared(sources)

            full = await index_incremental(
                conn,
                repo,
                tmp_path,
                full_analyzer,
                languages=registry.languages,
                analysis_version="force-full",
            )
            assert full.plan.full_rebuild
            await validate_snapshot(conn, full.snapshot_id)
            full_batch = await load_snapshot_batch(conn, full.snapshot_id)
            assert {e.id: e for e in updated.entities} == {
                e.id: e for e in full_batch.entities
            }
            # Rebuild the same repository after a detector version change, then compare exact canonical entities.
            import code_crawler.javascript_adapter as adapter_module

            monkeypatch.setattr(adapter_module, "VERSION", "test-upgrade")
            upgraded = AdapterRegistry(
                (
                    JavaSourceAdapter(profile="symbols"),
                    JavaScriptSourceAdapter(),
                    TypeScriptSourceAdapter(),
                )
            )
            rebuilt = await index_sources(conn, repo, tmp_path, upgraded)
            assert {
                "api.ts",
                "other.ts",
                "app.tsx",
                "types.ts",
                "tsconfig.json",
                "client.js",
            } <= set(rebuilt.plan.reanalyze)
            assert "A.java" not in rebuilt.plan.reanalyze
            await validate_snapshot(conn, rebuilt.snapshot_id)
            rebuilt_batch = await load_snapshot_batch(conn, rebuilt.snapshot_id)

            def normalized(batch):
                return {
                    e.id: e
                    for e in batch.entities
                    if not isinstance(e, SourceAnalysis)
                    and not isinstance(e, (Relation, ExternalReference))
                }

            assert normalized(updated) == normalized(rebuilt_batch)
        finally:
            await conn.close()

    asyncio.run(scenario())
