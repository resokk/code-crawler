import asyncio
from pathlib import Path

import asyncpg
import pytest
from test_openapi_java_bindings import (
    CONTROLLER,
    contract,
    handler,
    links,
    sql_controller,
)
from test_publication_cli import command

from code_crawler import db, openapi_adapter, repos, search, snapshots
from code_crawler.java_adapter import JavaSourceAdapter
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
    HttpSelector,
    RelationKind,
    SourceAnalysis,
    SourceFile,
)

pytestmark = pytest.mark.integration
FEIGN = """package client; import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping; import org.springframework.web.bind.annotation.PathVariable;
@FeignClient(name="loan-service", path="/v1") interface LoanClient { @GetMapping("/loans/{id}") String get(@PathVariable("id") String id); }"""


async def initialize(
    conn: asyncpg.Connection, root: Path, files: dict[str, str]
) -> None:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    root.mkdir(parents=True, exist_ok=True)
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "OpenAPI Java Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    for path, text in files.items():
        (root / path).write_text(text)
    await commit(root, "fixture")


async def commit(root: Path, message: str) -> None:
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", message, cwd=root)


def test_openapi_java_publish_read_trace_reuse_ambiguity_edit_delete_and_rollback(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await initialize(
                conn,
                tmp_path,
                {
                    "Controller.java": sql_controller(),
                    "api.json": contract(),
                    "LoanClient.java": FEIGN,
                },
            )
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="api-binding",
                    display_name="API",
                    source=str(tmp_path),
                ),
            )
            registry = AdapterRegistry(
                (JavaSourceAdapter(profile="execution"), OpenApiSourceAdapter())
            )

            async def publish():
                result = await index_sources(conn, repo, tmp_path, registry)
                await validate_snapshot(conn, result.snapshot_id)
                await publish_snapshot(
                    conn,
                    repo,
                    result.snapshot_id,
                    expected_snapshot_id=result.base_snapshot_id,
                )
                return result, await load_snapshot_batch(conn, result.snapshot_id)

            await conn.execute("SET plan_cache_mode='force_custom_plan'")
            first, original = await publish()
            assert await conn.fetchval("SHOW plan_cache_mode") == "force_custom_plan"
            link = handler(original)
            assert link.resolution.status == "RESOLVED"
            async with published_reader(conn, "api-binding") as view:
                page = await view.get_relations(
                    link.source.id, kinds=(RelationKind.OPENAPI_HANDLER,)
                )
                assert page.items == (link,)
            trace = await search.trace_dependency(
                conn,
                "api-binding",
                link.source.id,
                depth=3,
                relation_kinds=["OPENAPI_HANDLER", "CALLS", "EXECUTES_SQL"],
            )
            assert {("OPENAPI_HANDLER", 1), ("CALLS", 2), ("EXECUTES_SQL", 3)} <= {
                (row["relation_kind"], row["depth"]) for row in trace["items"]
            }
            assert trace["items"][0]["certainty"] == "INFERRED"
            assert (
                links(original, RelationKind.OPENAPI_RESPONSE_DTO)[0].resolution.status
                == "PARTIAL"
            )
            reuse, restored = await publish()
            assert not reuse.plan.reanalyze
            assert {e.id: e for e in restored.entities} == {
                e.id: e for e in original.entities
            }
            (tmp_path / "Other.java").write_text(
                CONTROLLER.replace("class Controller", "class Other").replace(
                    "class User {String name;}", ""
                )
            )
            await commit(tmp_path, "add competing controller")
            ambiguous, alternatives = await publish()
            assert "api.json" in ambiguous.plan.reanalyze
            assert handler(alternatives).resolution.status == "AMBIGUOUS"
            assert len(handler(alternatives).resolution.candidates) == 2
            trace = await search.trace_dependency(
                conn,
                "api-binding",
                link.source.id,
                depth=3,
                relation_kinds=["OPENAPI_HANDLER", "CALLS", "EXECUTES_SQL"],
            )
            assert (
                len(trace["items"]) == 1 and len(trace["items"][0]["candidates"]) == 2
            )
            (tmp_path / "Other.java").unlink()
            (tmp_path / "Controller.java").write_text(
                sql_controller().replace("GetMapping", "PostMapping")
            )
            await commit(tmp_path, "change HTTP method")
            changed, mismatch = await publish()
            assert "api.json" in changed.plan.reanalyze
            assert handler(mismatch).resolution.status == "UNRESOLVED"
            assert not links(mismatch, RelationKind.OPENAPI_RESPONSE_DTO)
            assert any(
                isinstance(e, ExternalReference)
                and isinstance(e.selector, HttpSelector)
                and e.selector.method == "GET"
                for e in mismatch.entities
            )
            (tmp_path / "Controller.java").write_text(sql_controller())
            await commit(tmp_path, "restore route")
            before, _ = await publish()
            count_before = await conn.fetchval("SELECT count(*) FROM ucm_snapshots")

            async def fail(*args, **kwargs):
                raise RuntimeError("injected OpenAPI binding failure")

            with monkeypatch.context() as patch:
                patch.setattr(openapi_adapter._Prepared, "with_catalogs", fail)
                with pytest.raises(
                    AdapterError, match="injected OpenAPI binding failure"
                ):
                    await index_sources(conn, repo, tmp_path, registry)
            assert (
                await conn.fetchval("SELECT count(*) FROM ucm_snapshots")
                == count_before
            )
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == before.snapshot_id
            (tmp_path / "application.yaml").write_text(
                "server.servlet.context-path: /different\n"
            )
            await commit(tmp_path, "add context prefix")
            context, context_mismatch = await publish()
            assert "api.json" in context.plan.reanalyze
            assert handler(context_mismatch).resolution.status == "UNRESOLVED"
            (tmp_path / "application.yaml").unlink()
            (tmp_path / "Controller.java").unlink()
            await commit(tmp_path, "delete controller")
            deleted, deferred = await publish()
            assert "api.json" in deleted.plan.reanalyze
            assert handler(deferred).resolution.status == "UNRESOLVED"
            assert not links(deferred, RelationKind.OPENAPI_JAVA_PARAMETER)
            assert any(
                isinstance(e, ExternalReference)
                and isinstance(e.selector, HttpSelector)
                and e.selector.service == "loan-service"
                for e in deferred.entities
            )
            assert {
                e.id: e
                for e in (await load_snapshot_batch(conn, first.snapshot_id)).entities
            } == {e.id: e for e in original.entities}
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_remote_only_http_target_does_not_change_local_deferred_refs(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            root_a, root_b = tmp_path / "a", tmp_path / "b"
            api = contract(path="/loans/{id}", base="https://loan-service/v1")
            await initialize(conn, root_a, {"LoanClient.java": FEIGN, "api.json": api})
            registry = AdapterRegistry(
                (JavaSourceAdapter(profile="calls"), OpenApiSourceAdapter())
            )
            repo_a = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="caller", display_name="Caller", source=str(root_a)
                ),
            )
            a = await index_sources(conn, repo_a, root_a, registry)
            await validate_snapshot(conn, a.snapshot_id)
            await publish_snapshot(
                conn, repo_a, a.snapshot_id, expected_snapshot_id=None
            )
            before = await load_snapshot_batch(conn, a.snapshot_id)
            assert handler(before).resolution.status == "UNRESOLVED"
            java = CONTROLLER.replace("/api", "/v1").replace(
                "/users/{uid}", "/loans/{uid}"
            )
            await initialize(conn, root_b, {"Controller.java": java, "api.json": api})
            repo_b = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="loan-service",
                    display_name="Loans",
                    source=str(root_b),
                ),
            )
            b = await index_sources(conn, repo_b, root_b, registry)
            await validate_snapshot(conn, b.snapshot_id)
            await publish_snapshot(
                conn, repo_b, b.snapshot_id, expected_snapshot_id=None
            )
            actual_remote = await load_snapshot_batch(conn, b.snapshot_id)
            assert handler(actual_remote).resolution.status == "RESOLVED"
            assert {e.id for e in before.entities}.isdisjoint(
                e.id for e in actual_remote.entities
            )
            again = await index_sources(conn, repo_a, root_a, registry)
            assert not again.plan.reanalyze
            await validate_snapshot(conn, again.snapshot_id)
            after = await load_snapshot_batch(conn, again.snapshot_id)
            assert {e.id: e for e in before.entities} == {
                e.id: e for e in after.entities
            }
            selectors = [
                e
                for e in after.entities
                if isinstance(e, ExternalReference)
                and isinstance(e.selector, HttpSelector)
            ]
            assert len(selectors) == 2
            assert all(
                e.selector.service == "loan-service"
                and e.selector.method == "GET"
                and e.selector.path == "/v1/loans/{id}"
                and e.resolution == "UNRESOLVED"
                for e in selectors
            )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_default_cli_publishes_http_bindings_and_feign(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await initialize(
                conn,
                tmp_path,
                {
                    "Controller.java": CONTROLLER,
                    "api.json": contract(),
                    "LoanClient.java": FEIGN,
                },
            )
            code, output = await command(
                database_url, "index", str(tmp_path), "--repository-key", "api-cli"
            )
            assert code == 0 and "PUBLISHED" in output, output
            repo = await conn.fetchval(
                "SELECT id FROM ucm_repositories WHERE repository_key='api-cli'"
            )
            snapshot = await snapshots.published_snapshot(conn, repo)
            batch = await load_snapshot_batch(conn, snapshot["id"])
            assert handler(batch).resolution.status == "RESOLVED"
            assert any(
                isinstance(e, ExternalReference)
                and isinstance(e.selector, HttpSelector)
                and e.selector.service == "loan-service"
                for e in batch.entities
            )
            files = {e.id: e.path for e in batch.entities if isinstance(e, SourceFile)}
            reports = {
                files[e.source_file_id]: e
                for e in batch.entities
                if isinstance(e, SourceAnalysis)
            }
            from code_crawler.kafka_java import VERSION as KAFKA_VERSION

            assert reports["Controller.java"].adapter_version == KAFKA_VERSION + ":2"
            assert reports["api.json"].adapter_version == "openapi/2"
            assert {
                cap.capability for cap in reports["Controller.java"].capabilities
            } >= {"java.http", "java.symbols"}
            assert {cap.capability for cap in reports["api.json"].capabilities} == {
                "openapi.java.bindings",
                "openapi.contracts",
            }
        finally:
            await conn.close()

    asyncio.run(scenario())
