import asyncio
import json
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.javascript_adapter import TypeScriptSourceAdapter
from code_crawler.openapi_adapter import OpenApiSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.reader import published_reader
from code_crawler.source_adapters import AdapterError, AdapterRegistry, index_sources
from code_crawler.ucm import (
    ExternalReference,
    Relation,
    RelationKind,
    SourceAnalysis,
    Value,
)

pytestmark = pytest.mark.integration

API = {
    "openapi": "3.2.0",
    "paths": {
        "/items": {
            "query": {
                "parameters": [
                    {"name": "q", "in": "querystring", "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "models.json#/$defs/Item"}
                            }
                        }
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {"Remote": {"$ref": "https://example.invalid/remote.json#/Thing"}}
    },
}


def test_openapi_publish_incremental_isolation_and_tsconfig(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for migration in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, migration)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "OpenAPI Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            files = {
                "api.json": json.dumps(API),
                "models.json": '{"$defs":{"Item":{"properties":{"next":{"$ref":"#/$defs/Item"}}}}}',
                "bad.yaml": "openapi: [",
                "package.json": "{}",
                "tsconfig.json": '{"compilerOptions":{"paths":{"@api":["./api"]}}}',
                "api.ts": "export function load() {}",
                "client.ts": 'import {load} from "@api"; export function run() { load(); }',
            }
            for path, text in files.items():
                (tmp_path / path).write_text(text)

            async def commit(message):
                await repos.git("add", ".", cwd=tmp_path)
                await repos.git("commit", "-m", message, cwd=tmp_path)

            await commit("fixture")
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="openapi-a", display_name="API", source=str(tmp_path)
                ),
            )
            registry = AdapterRegistry(
                (OpenApiSourceAdapter(), TypeScriptSourceAdapter(include_json=False))
            )
            first = await index_sources(conn, repo, tmp_path, registry)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            links = [
                e
                for e in batch.entities
                if isinstance(e, Relation)
                and e.relation_kind == RelationKind.OPENAPI_REF
            ]
            assert len(links) == 2 and all(
                e.resolution.status == "RESOLVED" for e in links
            )
            assert all(e.evidence and e.evidence[0].source_range for e in links)
            async with published_reader(conn, "openapi-a") as view:
                proof = await view.get_evidence(links[0].id)
                assert proof and proof[0].source is not None
            assert any(
                isinstance(e, Value) and e.name == "method" and e.literal == "QUERY"
                for e in batch.entities
            )
            assert any(isinstance(e, ExternalReference) for e in batch.entities)
            assert any(
                isinstance(e, Relation)
                and e.relation_kind == RelationKind.CALLS
                and e.resolution.status == "RESOLVED"
                for e in batch.entities
            )
            assert any(
                isinstance(e, SourceAnalysis) and e.diagnostics for e in batch.entities
            )
            reuse = await index_sources(conn, repo, tmp_path, registry)
            assert reuse.plan.reanalyze == ()
            await validate_snapshot(conn, reuse.snapshot_id)
            assert {
                e.id: e
                for e in (await load_snapshot_batch(conn, reuse.snapshot_id)).entities
            } == {e.id: e for e in batch.entities}
            (tmp_path / "models.json").write_text(
                '{"$defs":{"Item":{"type":["object","null"]}}}'
            )
            await commit("schema edit")
            edited = await index_sources(conn, repo, tmp_path, registry)
            assert {"api.json", "models.json"} <= set(edited.plan.reanalyze)
            assert "client.ts" not in edited.plan.reanalyze
            await validate_snapshot(conn, edited.snapshot_id)
            await publish_snapshot(
                conn, repo, edited.snapshot_id, expected_snapshot_id=first.snapshot_id
            )
            (tmp_path / "tsconfig.json").write_text(
                '{"compilerOptions":{"paths":{"@api":["./missing"]}}}'
            )
            await commit("config edit")
            config = await index_sources(conn, repo, tmp_path, registry)
            assert "client.ts" in config.plan.reanalyze
            await validate_snapshot(conn, config.snapshot_id)
            configured = await load_snapshot_batch(conn, config.snapshot_id)
            assert not any(
                isinstance(e, Relation)
                and e.relation_kind == RelationKind.CALLS
                and e.resolution.status == "RESOLVED"
                for e in configured.entities
            )
            (tmp_path / "models.json").unlink()
            await commit("schema delete")
            deleted = await index_sources(conn, repo, tmp_path, registry)
            assert "api.json" in deleted.plan.reanalyze
            await validate_snapshot(conn, deleted.snapshot_id)
            missing = await load_snapshot_batch(conn, deleted.snapshot_id)
            assert any(
                isinstance(e, Relation)
                and e.relation_kind == RelationKind.OPENAPI_REF
                and e.resolution.status == "UNRESOLVED"
                for e in missing.entities
            )
            await publish_snapshot(
                conn, repo, deleted.snapshot_id, expected_snapshot_id=edited.snapshot_id
            )
            # A second repository cannot supply the missing local target.
            other = tmp_path / "other"
            other.mkdir()
            await repos.git("init", cwd=other)
            await repos.git("config", "user.name", "Other", cwd=other)
            await repos.git("config", "user.email", "test@example.invalid", cwd=other)
            (other / "models.json").write_text(json.dumps(API))
            await repos.git("add", ".", cwd=other)
            await repos.git("commit", "-m", "other", cwd=other)
            repo_b = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="openapi-b", display_name="B", source=str(other)
                ),
            )
            result_b = await index_sources(conn, repo_b, other, registry)
            await validate_snapshot(conn, result_b.snapshot_id)
            await publish_snapshot(
                conn, repo_b, result_b.snapshot_id, expected_snapshot_id=None
            )
            other_batch = await load_snapshot_batch(conn, result_b.snapshot_id)
            assert {e.id for e in missing.entities}.isdisjoint(
                e.id for e in other_batch.entities
            )
            # A previously metadata-only fragment becomes reachable: catalog fingerprint changes.
            (tmp_path / "new.json").write_text('{"type":"object"}')
            await commit("unreferenced fragment")
            unreferenced = await index_sources(conn, repo, tmp_path, registry)
            await validate_snapshot(conn, unreferenced.snapshot_id)
            changed_api = json.loads(json.dumps(API))
            changed_api["components"]["schemas"]["New"] = {"$ref": "new.json"}
            (tmp_path / "api.json").write_text(json.dumps(changed_api))
            await commit("reference fragment")
            reachable = await index_sources(conn, repo, tmp_path, registry)
            assert "new.json" in reachable.plan.reanalyze
            await validate_snapshot(conn, reachable.snapshot_id)
            (tmp_path / "api.json").write_text(json.dumps(API))
            await commit("producer failure")

            async def fail(*args, **kwargs):
                raise RuntimeError("injected parser failure")

            monkeypatch.setattr(OpenApiSourceAdapter, "prepare", fail)
            with pytest.raises(AdapterError, match="injected parser failure"):
                await index_sources(conn, repo, tmp_path, registry)
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == deleted.snapshot_id
        finally:
            await conn.close()

    asyncio.run(scenario())
