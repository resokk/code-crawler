import asyncio
import json
from pathlib import Path

import asyncpg
import pytest
from test_bpmn_java_bindings import DELEGATE, IMPORTS, binding, bpmn, relations
from test_publication_cli import command

from code_crawler import bpmn_adapter, db, repos, search, snapshots
from code_crawler.bpmn_adapter import BpmnSourceAdapter
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.reader import published_reader
from code_crawler.source_adapters import AdapterError, AdapterRegistry, index_sources
from code_crawler.ucm import ExternalReference, RelationKind, SourceAnalysis, SourceFile

pytestmark = pytest.mark.integration
SQL_DELEGATE = (
    IMPORTS
    + """import java.sql.Statement;
@Component("charge") class Charge implements JavaDelegate {
 public void execute(DelegateExecution e) throws Exception {
  Statement db=(Statement)e.getVariable("db"); Object amount=e.getVariable("amount");
  e.setVariable("result", amount); db.executeUpdate("update orders set state='done'");
 }
}"""
)
XML = bpmn("""<serviceTask id="task" c:delegateExpression="${charge}"><extensionElements><c:inputOutput>
<c:inputParameter name="amount">${order.total}</c:inputParameter>
<c:outputParameter name="orderId">${result}</c:outputParameter>
</c:inputOutput></extensionElements></serviceTask>""")
REMOTE_XML = bpmn("""<serviceTask id="external"><extensionElements><z:taskDefinition type="remote-job"/></extensionElements></serviceTask>
<callActivity id="remoteCall" calledElement="remote-process"/>""")


async def initialize(
    conn: asyncpg.Connection, root: Path, files: dict[str, str]
) -> None:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    root.mkdir(parents=True, exist_ok=True)
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "BPMN Java Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    for path, text in files.items():
        (root / path).write_text(text)
    await commit(root, "fixture")


async def commit(root: Path, message: str) -> None:
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", message, cwd=root)


def test_bpmn_java_publish_read_reuse_ambiguity_recovery_deletion_and_isolation(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        root = tmp_path / "a"
        try:
            await initialize(
                conn,
                root,
                {"Charge.java": SQL_DELEGATE, "p.bpmn": XML, "remote.bpmn": REMOTE_XML},
            )
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="binding-a",
                    display_name="Binding A",
                    source=str(root),
                ),
            )
            registry = AdapterRegistry(
                (JavaSourceAdapter(profile="execution"), BpmnSourceAdapter())
            )

            async def publish(registry=registry):
                result = await index_sources(conn, repo, root, registry)
                await validate_snapshot(conn, result.snapshot_id)
                await publish_snapshot(
                    conn,
                    repo,
                    result.snapshot_id,
                    expected_snapshot_id=result.base_snapshot_id,
                )
                return result, await load_snapshot_batch(conn, result.snapshot_id)

            first, original = await publish()
            local = next(
                e
                for e in relations(original, RelationKind.BPMN_HANDLER)
                if e.resolution.target
            )
            sql = relations(original, RelationKind.EXECUTES_SQL)
            assert len(sql) == 1 and sql[0].source.id == local.resolution.target.id
            assert len(relations(original, RelationKind.BPMN_VARIABLE_BINDING)) == 2
            trace = await search.trace_dependency(
                conn,
                "binding-a",
                local.source.id,
                depth=2,
                relation_kinds=["BPMN_HANDLER", "EXECUTES_SQL"],
            )
            assert [row["relation_kind"] for row in trace["items"]] == [
                "BPMN_HANDLER",
                "EXECUTES_SQL",
            ]
            assert trace["items"][0]["certainty"] == "INFERRED"
            async with published_reader(conn, "binding-a") as view:
                page = await view.get_relations(
                    local.source.id, kinds=(RelationKind.BPMN_HANDLER,)
                )
                assert page.items[0] == local
            reused, restored = await publish()
            assert not reused.plan.reanalyze
            assert {e.id: e for e in restored.entities} == {
                e.id: e for e in original.entities
            }
            (root / "Other.java").write_text(DELEGATE.replace("Charge", "Other"))
            await commit(root, "add competing bean")
            ambiguous, candidates = await publish()
            assert {"p.bpmn", "remote.bpmn", "Other.java"} <= set(
                ambiguous.plan.reanalyze
            )
            assert any(
                e.resolution.status == "AMBIGUOUS" and len(e.resolution.candidates) == 2
                for e in relations(candidates, RelationKind.BPMN_HANDLER)
            )
            trace = await search.trace_dependency(
                conn,
                "binding-a",
                local.source.id,
                depth=2,
                relation_kinds=["BPMN_HANDLER", "EXECUTES_SQL"],
            )
            assert len(trace["items"]) == 1
            assert len(trace["items"][0]["candidates"]) == 2
            (root / "Other.java").unlink()
            await commit(root, "remove competing bean")
            _, unique = await publish()
            assert (
                sum(
                    e.resolution.status == "RESOLVED"
                    for e in relations(unique, RelationKind.BPMN_HANDLER)
                )
                == 1
            )
            (root / "Charge.java").write_text(
                SQL_DELEGATE.replace('@Component("charge")', '@Component("renamed")')
            )
            await commit(root, "rename bean only")
            renamed, unresolved = await publish()
            assert "p.bpmn" in renamed.plan.reanalyze
            assert all(
                e.resolution.target is None
                for e in relations(unresolved, RelationKind.BPMN_HANDLER)
            )
            assert not relations(unresolved, RelationKind.BPMN_READS_VARIABLE)
            assert any(
                isinstance(e, ExternalReference)
                and e.selector.qualified_name == "bpmn.delegateExpression::${charge}"
                for e in unresolved.entities
            )
            (root / "Charge.java").write_text(SQL_DELEGATE)
            await commit(root, "restore bean")
            _, unique = await publish()
            pinned = AdapterRegistry(
                (
                    JavaSourceAdapter(profile="execution"),
                    BpmnSourceAdapter(profile="camunda8"),
                )
            )
            changed_profile, unsupported = await publish(pinned)
            assert set(changed_profile.plan.reanalyze) == {"p.bpmn", "remote.bpmn"}
            assert all(
                e.resolution.target is None
                for e in relations(unsupported, RelationKind.BPMN_HANDLER)
            )
            before, _ = await publish()
            snapshots_before = await conn.fetchval("SELECT count(*) FROM ucm_snapshots")

            async def fail(*args, **kwargs):
                raise RuntimeError("injected binding failure")

            with monkeypatch.context() as patch:
                patch.setattr(bpmn_adapter._PreparedBpmn, "with_catalogs", fail)
                with pytest.raises(AdapterError, match="injected binding failure"):
                    await index_sources(conn, repo, root, registry)
            assert (
                await conn.fetchval("SELECT count(*) FROM ucm_snapshots")
                == snapshots_before
            )
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == before.snapshot_id
            (root / "Charge.java").write_text("class Broken {")
            await commit(root, "malformed Java")
            with pytest.raises(AdapterError):
                await index_sources(conn, repo, root, registry)
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == before.snapshot_id
            (root / "Charge.java").unlink()
            await commit(root, "delete Java handler")
            deleted, external = await publish()
            assert "p.bpmn" in deleted.plan.reanalyze
            assert not relations(external, RelationKind.BPMN_READS_VARIABLE)
            assert not relations(external, RelationKind.BPMN_WRITES_VARIABLE)
            assert all(
                e.resolution.status == "UNRESOLVED"
                for e in relations(external, RelationKind.BPMN_HANDLER)
            )
            # Publishing actual targets elsewhere must not affect repository A's catalog or reuse.
            other_root = tmp_path / "b"
            worker = """package remote; import io.camunda.spring.client.annotation.JobWorker;
            class Worker { @JobWorker(type="remote-job") public void work() {} }"""
            await initialize(
                conn,
                other_root,
                {
                    "Charge.java": SQL_DELEGATE,
                    "Worker.java": worker,
                    "process.bpmn": '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"><process id="remote-process"/></definitions>',
                },
            )
            other_repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="binding-b",
                    display_name="Binding B",
                    source=str(other_root),
                ),
            )
            other = await index_sources(conn, other_repo, other_root, registry)
            await validate_snapshot(conn, other.snapshot_id)
            await publish_snapshot(
                conn, other_repo, other.snapshot_id, expected_snapshot_id=None
            )
            other_batch = await load_snapshot_batch(conn, other.snapshot_id)
            assert {e.id for e in external.entities}.isdisjoint(
                e.id for e in other_batch.entities
            )
            final, same_external = await publish()
            assert not final.plan.reanalyze
            assert {e.id: e for e in same_external.entities} == {
                e.id: e for e in external.entities
            }
            assert {
                e.selector.qualified_name
                for e in same_external.entities
                if isinstance(e, ExternalReference)
            } >= {
                "bpmn.worker::remote-job",
                "bpmn.process::remote-process",
                "bpmn.delegateExpression::${charge}",
            }
            assert {
                e.id: e
                for e in (await load_snapshot_batch(conn, first.snapshot_id)).entities
            } == {e.id: e for e in original.entities}
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_bpmn_profile_cli_publication_and_persisted_diagnostics(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await initialize(
                conn,
                tmp_path,
                {"Charge.java": DELEGATE, "p.bpmn": XML, "broken.bpmn": "<broken"},
            )
            code, output = await command(
                database_url,
                "index-sources",
                str(tmp_path),
                "--repository-key",
                "binding-cli",
                "--bpmn-profile",
                "camunda7",
                "--publish",
            )
            assert code == 0 and "PUBLISHED" in output, output
            repo = await conn.fetchval(
                "SELECT id FROM ucm_repositories WHERE repository_key='binding-cli'"
            )
            snapshot = await snapshots.published_snapshot(conn, repo)
            batch = await load_snapshot_batch(conn, snapshot["id"])
            assert binding(batch).resolution.status == "RESOLVED"
            files = {e.id: e.path for e in batch.entities if isinstance(e, SourceFile)}
            reports = {
                files[e.source_file_id]: e
                for e in batch.entities
                if isinstance(e, SourceAnalysis)
            }
            assert reports["p.bpmn"].analysis_version.startswith(
                "bpmn/2:camunda7:java.bpmn.handlers/1:"
            )
            assert reports["broken.bpmn"].diagnostics[0].code == "bpmn.INVALID_XML"
            parameters = json.loads(
                await conn.fetchval(
                    "SELECT parameters FROM ingest_jobs WHERE repository_id=$1", repo
                )
            )
            assert parameters["bpmn_profile"] == "camunda7"
            assert parameters["java_profile"] == "orm"
        finally:
            await conn.close()

    asyncio.run(scenario())
