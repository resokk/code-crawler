import asyncio
import hashlib
import json
import shutil

import asyncpg
import pytest
from test_publication_cli import command
from test_structural_search import REPO, SERVICE

from code_crawler import repos, search, snapshots
from code_crawler.database_resolution import ConnectionAssignment, ConnectionContext
from code_crawler.database_schema import (
    ColumnDefinition,
    SchemaDefinition,
    SchemaImport,
    TableDefinition,
)
from code_crawler.incremental import SourceInput
from code_crawler.java_symbols import extract
from code_crawler.publication import load_snapshot_batch
from code_crawler.reader import published_reader
from code_crawler.ucm import (
    DatabaseAccess,
    DatabaseObject,
    EntityType,
    RelationKind,
    SourceAnalysis,
    SourceFile,
    Symbol,
    logical_id,
)

pytestmark = pytest.mark.integration


def test_mixed_cli_publish_read_archive_reuse_and_publication_failure(
    database_url, tmp_path
):
    async def run():
        root = tmp_path / "repository"
        root.mkdir()
        conn = await asyncpg.connect(database_url)
        try:
            code, output = await command(database_url, "db", "init")
            assert code == 0, output
            await repos.git("init", cwd=root)
            await repos.git("config", "user.name", "Canonical e2e", cwd=root)
            await repos.git("config", "user.email", "test@example.invalid", cwd=root)
            repo_text = REPO.replace(
                "public class Repo {",
                'public class Repo {\n    static final String UNUSED="DELETE FROM audit_log";',
            )
            content = ("// я\n" + repo_text).replace("\n", "\r\n").encode()
            (root / "Repo.java").write_bytes(content)
            (root / "Service.java").write_text(SERVICE)
            (root / "script.groovy").write_text("def q='select id from groovy_only'")
            plp = root / "C/methods/M/src/execute.plp"
            plp.parent.mkdir(parents=True)
            plp.write_text("begin [A] := 1; end;")
            await repos.git("add", ".", cwd=root)
            await repos.git("commit", "-m", "mixed fixture", cwd=root)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="mixed", display_name="mixed", source=str(root)
                ),
            )
            source = SourceFile(
                repository_id=str(repo),
                logical_key="Repo.java",
                id=logical_id(str(repo), EntityType.SOURCE_FILE, "Repo.java"),
                name="Repo.java",
                path="Repo.java",
                language="java",
                content_sha256=hashlib.sha256(content).hexdigest(),
            )
            connection = next(
                e
                for e in extract(SourceInput(source, content)).analysis.entities
                if isinstance(e, Symbol)
                and e.symbol_kind == "FIELD"
                and e.name == "connection"
            )
            manifest = SchemaImport(
                database_key="app-db",
                version_key="v1",
                dialect="postgres",
                catalog_name="app",
                schemas=(
                    SchemaDefinition(
                        name="public",
                        tables=(
                            TableDefinition(
                                name="users",
                                columns=tuple(
                                    ColumnDefinition(
                                        name=name,
                                        ordinal=i,
                                        data_type=kind,
                                        nullable=False,
                                    )
                                    for i, (name, kind) in enumerate(
                                        (
                                            ("id", "text"),
                                            ("name", "text"),
                                            ("age", "int"),
                                        ),
                                        1,
                                    )
                                ),
                            ),
                        ),
                    ),
                ),
            )
            manifest_path = tmp_path / "schema.json"
            manifest_path.write_text(manifest.model_dump_json())
            code, output = await command(
                database_url, "schema", "import-manifest", str(manifest_path)
            )
            assert code == 0, output
            assignment = ConnectionAssignment(
                symbol_key=connection.logical_key,
                context=ConnectionContext(
                    connection_key="primary",
                    database_key="app-db",
                    version_key="v1",
                    search_path=("public",),
                ),
            )
            connections = tmp_path / "connections.json"
            connections.write_text(json.dumps([assignment.model_dump(mode="json")]))
            args = [
                "index-sources",
                str(root),
                "--repository-key",
                "mixed",
                "--connections",
                str(connections),
            ]
            code, output = await command(database_url, *args, "--publish")
            assert code == 0 and "PUBLISHED" in output, output
            first = (await snapshots.published_snapshot(conn, repo))["id"]
            first_batch = await load_snapshot_batch(conn, first)
            reports = [e for e in first_batch.entities if isinstance(e, SourceAnalysis)]
            assert {r.adapter_key for r in reports} == {"java.orm", "groovy", "plplus"}
            assert not any(
                d.severity == "ERROR" for r in reports for d in r.diagnostics
            )
            async with published_reader(conn, "mixed") as view:
                handle = (
                    await search.search_symbols(conn, "mixed", "app.Service.handle")
                )["items"][0]["id"]
                calls = await view.get_relations(handle, kinds=(RelationKind.CALLS,))
                matching_calls = [
                    r
                    for r in calls.items
                    if r.resolution.target
                    and (await view.get_entity(r.resolution.target.id)).name == "load"
                ]
                call = matching_calls[0]
                load = await view.get_entity(call.resolution.target.id)
                execution_relation = (
                    await view.get_relations(
                        load.id, kinds=(RelationKind.EXECUTES_SQL,)
                    )
                ).items[0]
                execution = await view.get_sql_execute(
                    execution_relation.resolution.target.id
                )
                statement_relation = (
                    await view.get_relations(
                        execution.id, kinds=(RelationKind.EXECUTES_STATEMENT,)
                    )
                ).items[0]
                statement = await view.get_sql_statement(
                    statement_relation.resolution.target.id
                )
                assert statement.operation == "SELECT" and "users" in statement.text
                effects = await view.get_relations(
                    statement.id, kinds=(RelationKind.READS_FROM,)
                )
                accesses = [
                    await view.get_data_access(r.resolution.target.id)
                    for r in effects.items
                ]
                access = next(a for a in accesses if a.object_kind == "TABLE")
                assert access.table_name.normalized == "users"
                contextual = (
                    await view.get_relations(
                        access.id, kinds=(RelationKind.CONTEXTUALIZES_ACCESS,)
                    )
                ).items[0]
                db_access = await view.get_entity(contextual.resolution.target.id)
                assert isinstance(db_access, DatabaseAccess)
                physical = (
                    await view.get_relations(
                        db_access.id, kinds=(RelationKind.RESOLVES_DATABASE_OBJECT,)
                    )
                ).items[0]
                db_object = await view.get_entity(physical.resolution.target.id)
                assert (
                    isinstance(db_object, DatabaseObject)
                    and db_object.database_key == "app-db"
                    and db_object.table_name == "users"
                )
                bindings = (
                    await view.get_relations(
                        execution.id, kinds=(RelationKind.HAS_SQL_BINDING,)
                    )
                ).items
                assert bindings
                assert (
                    await view.get_sql_binding(bindings[0].resolution.target.id)
                ).position == 1
                unused = (await search.find_table_writers(conn, "mixed", "audit_log"))[
                    "items"
                ]
                assert unused and all(not item["executions"] for item in unused)
                for item in unused:
                    assert not (
                        await view.get_relations(
                            item["statement_id"],
                            direction="in",
                            kinds=(RelationKind.EXECUTES_STATEMENT,),
                        )
                    ).items
                proof = (await view.get_evidence(call.id))[0]
                assert proof.source.content == b"repo.load(id)"
                assert proof.source.provenance.snapshot_id == first
                assert call.coverage.status == "PARTIAL"
                sql_proof = (await view.get_evidence(execution_relation.id))[0]
                assert b"executeQuery" in sql_proof.source.content
                statement_id = statement.id
                execution_proof_id = execution_relation.id
            code, output = await command(database_url, *args, "--publish")
            assert code == 0, output
            second = (await snapshots.published_snapshot(conn, repo))["id"]
            second_batch = await load_snapshot_batch(conn, second)
            assert first != second
            assert {e.id: e for e in first_batch.entities} == {
                e.id: e for e in second_batch.entities
            }
            # BUILDING facts remain invisible; failure after retiring the old version rolls back.
            (root / "Repo.java").write_bytes(content.replace(b"users", b"staff"))
            code, output = await command(database_url, *args)
            assert code == 0, output
            target = await conn.fetchval(
                "SELECT id FROM ucm_snapshots WHERE state='BUILDING'"
            )
            await conn.execute(
                "CREATE FUNCTION reject_e2e_publish() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected publication failure'; END; $$"
            )
            await conn.execute(
                f"CREATE TRIGGER reject_e2e_publish BEFORE UPDATE OF state ON ucm_snapshots FOR EACH ROW WHEN (NEW.id='{target}'::uuid AND NEW.state='PUBLISHED') EXECUTE FUNCTION reject_e2e_publish()"
            )
            code, output = await command(
                database_url,
                "snapshot",
                "publish",
                str(target),
                "--expected-current",
                str(second),
            )
            assert code == 1 and "injected publication failure" in output
            assert (await snapshots.published_snapshot(conn, repo))["id"] == second
            assert (
                await conn.fetchval(
                    "SELECT state FROM ucm_snapshots WHERE id=$1", target
                )
                == "READY"
            )
            await asyncio.to_thread(shutil.rmtree, root)
            async with published_reader(conn, "mixed") as view:
                assert view.snapshot_id == second
                assert "users" in (await view.get_sql_statement(statement_id)).text
                proof = (await view.get_evidence(execution_proof_id))[0]
                assert b"executeQuery" in proof.source.content
                assert (
                    proof.source.provenance.content_sha256
                    == hashlib.sha256(content).hexdigest()
                )
        finally:
            await conn.close()

    asyncio.run(run())
