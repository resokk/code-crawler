import asyncio
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, repos, snapshots
from code_crawler.bpmn_adapter import BPMN, BpmnSourceAdapter
from code_crawler.java_adapter import JavaSourceAdapter
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

XML = f'''<definitions xmlns="{BPMN}" xmlns:c="http://camunda.org/schema/1.0/bpmn">
<process id="p"><exclusiveGateway id="g"/><serviceTask id="t" c:topic="remote-worker"/>
<userTask id="u"/><callActivity id="remote" calledElement="remote-process"/>
<sequenceFlow id="one" sourceRef="g" targetRef="t"><conditionExpression>${{x &gt; 0}}</conditionExpression></sequenceFlow>
<sequenceFlow id="two" sourceRef="g" targetRef="u"><conditionExpression>${{x &lt;= 0}}</conditionExpression></sequenceFlow>
</process></definitions>'''


def test_bpmn_publication_roundtrip_reuse_edit_delete_isolation_and_rollback(
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "BPMN Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            for path, text in {
                "process.bpmn": XML,
                "Broken.bpmn": "<broken",
                "unsafe.bpmn20.xml": '<!DOCTYPE x SYSTEM "file:///etc/passwd"><x/>',
                "unrelated.xml": "<configuration/>",
                "A.java": "class A {}",
            }.items():
                (tmp_path / path).write_text(text)

            async def commit(message: str) -> None:
                await repos.git("add", ".", cwd=tmp_path)
                await repos.git("commit", "-m", message, cwd=tmp_path)

            await commit("fixture")
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="bpmn-a", display_name="BPMN A", source=str(tmp_path)
                ),
            )
            registry = AdapterRegistry(
                (BpmnSourceAdapter(), JavaSourceAdapter(profile="symbols"))
            )
            first = await index_sources(conn, repo, tmp_path, registry)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            flows = [
                e
                for e in batch.entities
                if isinstance(e, Relation)
                and e.relation_kind
                in (RelationKind.BPMN_FLOW_SOURCE, RelationKind.BPMN_FLOW_TARGET)
            ]
            assert len(flows) == 4
            assert any(
                isinstance(e, ExternalReference)
                and e.selector.qualified_name == "bpmn.worker::remote-worker"
                for e in batch.entities
            )
            paths = {e.id: e.path for e in batch.entities if isinstance(e, SourceFile)}
            reports = {
                paths[e.source_file_id]: e
                for e in batch.entities
                if isinstance(e, SourceAnalysis)
            }
            assert reports["Broken.bpmn"].diagnostics[0].code == "bpmn.INVALID_XML"
            assert (
                reports["unsafe.bpmn20.xml"].diagnostics[0].code == "bpmn.INVALID_XML"
            )
            assert reports["unrelated.xml"].capabilities[0].status == "UNSUPPORTED"
            reuse = await index_sources(conn, repo, tmp_path, registry)
            assert not reuse.plan.reanalyze
            await validate_snapshot(conn, reuse.snapshot_id)
            restored = await load_snapshot_batch(conn, reuse.snapshot_id)
            assert {e.id: e for e in restored.entities} == {
                e.id: e for e in batch.entities
            }
            # A second repository publishes independently, with disjoint entity identities.
            root_b = tmp_path.with_name(tmp_path.name + "-b")
            root_b.mkdir()
            await repos.git("init", cwd=root_b)
            await repos.git("config", "user.name", "BPMN Test", cwd=root_b)
            await repos.git("config", "user.email", "test@example.invalid", cwd=root_b)
            (root_b / "target.bpmn").write_text(
                f'<definitions xmlns="{BPMN}"><process id="remote-process"/></definitions>'
            )
            await repos.git("add", ".", cwd=root_b)
            await repos.git("commit", "-m", "remote process", cwd=root_b)
            repo_b = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="bpmn-b", display_name="BPMN B", source=str(root_b)
                ),
            )
            other = await index_sources(conn, repo_b, root_b, registry)
            await validate_snapshot(conn, other.snapshot_id)
            await publish_snapshot(
                conn, repo_b, other.snapshot_id, expected_snapshot_id=None
            )
            other_batch = await load_snapshot_batch(conn, other.snapshot_id)
            assert {e.id for e in batch.entities}.isdisjoint(
                e.id for e in other_batch.entities
            )
            (tmp_path / "process.bpmn").write_text(
                XML.replace('targetRef="t"', 'targetRef="missing"')
            )
            await commit("invalid endpoint")
            changed = await index_sources(conn, repo, tmp_path, registry)
            assert set(changed.plan.reanalyze) == {"process.bpmn"}
            await validate_snapshot(conn, changed.snapshot_id)
            updated = await load_snapshot_batch(conn, changed.snapshot_id)
            assert (
                sum(
                    isinstance(e, Relation)
                    and e.relation_kind
                    in (RelationKind.BPMN_FLOW_SOURCE, RelationKind.BPMN_FLOW_TARGET)
                    for e in updated.entities
                )
                == 2
            )
            assert any(
                isinstance(e, SourceAnalysis)
                and any(d.code == "bpmn.INVALID_FLOW" for d in e.diagnostics)
                for e in updated.entities
            )
            await publish_snapshot(
                conn, repo, changed.snapshot_id, expected_snapshot_id=first.snapshot_id
            )
            # Failed producer leaves the published pointer and facts intact.
            before = await conn.fetchval(
                "SELECT snapshot_id FROM ucm_repository_publications WHERE repository_id=$1",
                repo,
            )
            (tmp_path / "process.bpmn").write_text(XML)
            await commit("restore input")

            async def fail(*args, **kwargs):
                raise RuntimeError("injected producer failure")

            from code_crawler import bpmn_adapter

            with monkeypatch.context() as patch:
                patch.setattr(bpmn_adapter._PreparedBpmn, "__call__", fail)
                with pytest.raises(ValueError, match="injected producer failure"):
                    await index_sources(conn, repo, tmp_path, registry)
            assert (
                await conn.fetchval(
                    "SELECT snapshot_id FROM ucm_repository_publications WHERE repository_id=$1",
                    repo,
                )
                == before
            )
            (tmp_path / "process.bpmn").unlink()
            await commit("delete BPMN")
            deleted = await index_sources(conn, repo, tmp_path, registry)
            await validate_snapshot(conn, deleted.snapshot_id)
            remaining = await load_snapshot_batch(conn, deleted.snapshot_id)
            assert not any(isinstance(e, ExternalReference) for e in remaining.entities)
            assert {
                e.id: e
                for e in (await load_snapshot_batch(conn, first.snapshot_id)).entities
            } == {e.id: e for e in batch.entities}
        finally:
            await conn.close()

    asyncio.run(scenario())
