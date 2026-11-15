import asyncio
from pathlib import Path

import asyncpg
import pytest
from test_publication_cli import command

from code_crawler import db, repos, snapshots
from code_crawler.bpmn_adapter import BPMN, BpmnSourceAdapter
from code_crawler.groovy_adapter import GroovySourceAdapter
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.kafka_adapter import KafkaSourceAdapter
from code_crawler.plplus_adapter import PlplusSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.reader import published_reader
from code_crawler.source_adapters import AdapterError, AdapterRegistry, index_sources
from code_crawler.source_evidence import read_source_file
from code_crawler.ucm import (
    ExternalReference,
    Relation,
    RelationKind,
    SourceAnalysis,
    SourceFile,
    SqlExecute,
    SqlStatement,
)
from code_crawler.vbscript_adapter import VbscriptSourceAdapter

pytestmark = pytest.mark.integration

SCRIPT = """Option Explicit
Sub Remove(id)
Dim cn, q
Set cn=CreateObject("ADODB.Connection")
cn.Open "not-a-real-connection"
q="DELETE FROM users WHERE id=1"
cn.Execute q
End Sub
Call REMOVE(1)
Function Unused()
Unused="DELETE FROM never_executed"
End Function
Call Remote.Invoke()
"""


class VersionTwo(VbscriptSourceAdapter):
    @property
    def descriptor(self):
        return super().descriptor.model_copy(update={"version": "2"})


def registry(adapter=None):
    return AdapterRegistry(
        (
            KafkaSourceAdapter(JavaSourceAdapter(profile="symbols")),
            GroovySourceAdapter(),
            PlplusSourceAdapter(),
            BpmnSourceAdapter(),
            adapter or VbscriptSourceAdapter(),
        )
    )


async def commit(root: Path) -> None:
    await repos.git("add", "-A", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)


async def published(conn, repo, result):
    assert await validate_snapshot(conn, result.snapshot_id) > 0
    await publish_snapshot(
        conn, repo, result.snapshot_id, expected_snapshot_id=result.base_snapshot_id
    )
    return await load_snapshot_batch(conn, result.snapshot_id)


def test_vbscript_cli_publication_mixed_sources_evidence_and_incremental(
    database_url, tmp_path
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "VBScript Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            sources = {
                "A.java": "class A {}",
                "Job.groovy": "class Job { def run() { 1 } }",
                "exports/CLIENT/methods/EDIT/src/execute.plp": "begin null; end;",
                "process.bpmn": f'<definitions xmlns="{BPMN}"><process id="p"><startEvent id="s"/></process></definitions>',
                "Script.VbS": SCRIPT,
            }
            for path, content in sources.items():
                target = tmp_path / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            await commit(tmp_path)
            code, output = await command(
                database_url,
                "index-sources",
                str(tmp_path),
                "--repository-key",
                "vbscript-mixed",
                "--java-profile",
                "symbols",
                "--publish",
            )
            assert code == 0 and "PUBLISHED" in output, output
            repo = await conn.fetchval(
                "SELECT id FROM ucm_repositories WHERE repository_key='vbscript-mixed'"
            )
            first = (await snapshots.published_snapshot(conn, repo))["id"]
            batch = await load_snapshot_batch(conn, first)
            reports = [e for e in batch.entities if isinstance(e, SourceAnalysis)]
            assert {e.adapter_key for e in reports} == {
                "java.symbols",
                "groovy",
                "plplus",
                "bpmn",
                "vbscript",
            }
            assert not any(
                d.severity == "ERROR" for e in reports for d in e.diagnostics
            )
            assert len([e for e in batch.entities if isinstance(e, SqlExecute)]) == 1
            assert any(
                isinstance(e, ExternalReference)
                and e.selector.qualified_name == "remote.invoke"
                for e in batch.entities
            )
            link = next(
                e
                for e in batch.entities
                if isinstance(e, Relation)
                and e.relation_kind == RelationKind.EXECUTES_STATEMENT
            )
            async with published_reader(conn, "vbscript-mixed") as view:
                assert (
                    await view.get_sql_statement(link.resolution.target.id)
                ).text == "DELETE FROM users WHERE id=1"
                proof = (await view.get_evidence(link.id))[0]
                assert proof.source.content == b"cn.Execute q"
                assert proof.source.provenance.snapshot_id == first
            vbs_file = next(
                e
                for e in batch.entities
                if isinstance(e, SourceFile) and e.language == "vbscript"
            )
            reused = await index_sources(conn, repo, tmp_path, registry())
            assert reused.plan.reanalyze == ()
            restored = await published(conn, repo, reused)
            assert {e.id: e for e in restored.entities} == {
                e.id: e for e in batch.entities
            }

            target = tmp_path / "Script.VbS"
            target.write_text(SCRIPT.replace("FROM users", "FROM accounts"))
            await commit(tmp_path)
            changed = await index_sources(conn, repo, tmp_path, registry())
            assert changed.plan.reanalyze == ("Script.VbS",)
            changed_batch = await published(conn, repo, changed)
            assert any(
                isinstance(e, SqlStatement)
                and e.text == "DELETE FROM accounts WHERE id=1"
                for e in changed_batch.entities
            )
            assert (
                await read_source_file(conn, repo, first, vbs_file.id)
            ).content == SCRIPT.encode()

            versioned = await index_sources(
                conn, repo, tmp_path, registry(VersionTwo())
            )
            assert versioned.plan.reanalyze == ("Script.VbS",)
            assert set(versioned.plan.reused) == set(sources) - {"Script.VbS"}
            versioned_batch = await published(conn, repo, versioned)
            # Forced analyzer reanalysis must reproduce all canonical facts; only the report version changes.
            assert {
                e.id: e
                for e in changed_batch.entities
                if not isinstance(e, SourceAnalysis)
            } == {
                e.id: e
                for e in versioned_batch.entities
                if not isinstance(e, SourceAnalysis)
            }
            assert (
                next(
                    e
                    for e in versioned_batch.entities
                    if isinstance(e, SourceAnalysis) and e.adapter_key == "vbscript"
                ).adapter_version
                == "2"
            )

            before = await conn.fetchval("SELECT count(*) FROM ucm_snapshots")
            target.write_text("Sub Broken(\n")
            await commit(tmp_path)
            with pytest.raises(AdapterError) as failure:
                await index_sources(conn, repo, tmp_path, registry(VersionTwo()))
            assert failure.value.issues[0].path == "Script.VbS"
            assert failure.value.issues[0].diagnostic.source_range is not None
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == versioned.snapshot_id
            assert await conn.fetchval("SELECT count(*) FROM ucm_snapshots") == before
            assert (
                b"DELETE FROM accounts"
                in (
                    await read_source_file(
                        conn, repo, versioned.snapshot_id, vbs_file.id
                    )
                ).content
            )

            target.unlink()
            await commit(tmp_path)
            deleted = await index_sources(conn, repo, tmp_path, registry(VersionTwo()))
            assert deleted.plan.deleted == ("Script.VbS",)
            deleted_batch = await published(conn, repo, deleted)
            assert not any(isinstance(e, SqlExecute) for e in deleted_batch.entities)
            assert not any(
                isinstance(e, SourceAnalysis) and e.adapter_key == "vbscript"
                for e in deleted_batch.entities
            )
        finally:
            await conn.close()

    asyncio.run(run())
