import asyncio

import asyncpg
import pytest
from test_structural_search import publish

from code_crawler import reader as readers
from code_crawler import search
from code_crawler.groovy_adapter import GroovySourceAdapter
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.jobs import collect_garbage
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.reader import published_reader
from code_crawler.source_adapters import AdapterRegistry, index_sources
from code_crawler.source_evidence import SourceUnavailableError
from code_crawler.ucm import (
    DataAccess,
    ExternalReference,
    Relation,
    RelationKind,
    SqlBinding,
    SqlExecute,
    SqlStatement,
    Symbol,
)

pytestmark = pytest.mark.integration


def test_full_typed_reads_roundtrip_and_scoped_relations(database_url, tmp_path):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            (tmp_path / "query.groovy").write_text(
                'def table="logs"; def q="select id from $table"'
            )
            for name in ("one", "two"):
                directory = tmp_path / name
                directory.mkdir()
                (directory / "A.java").write_text(
                    "package ambiguous; class A { void hit() {} }"
                )
            (tmp_path / "Use.java").write_text(
                "package ambiguous; class Use { void run(A a){ a.hit(); } }"
            )
            await publish(conn, tmp_path)
            async with published_reader(conn, "app") as view:
                batch = await load_snapshot_batch(conn, view.snapshot_id)
                catalog = {e.id: e for e in batch.entities}
                for entity in batch.entities:
                    assert await view.get_entity(entity.id) == entity
                ambiguous = next(
                    e
                    for e in batch.entities
                    if isinstance(e, Relation)
                    and e.relation_kind == RelationKind.CALLS
                    and e.resolution.status == "AMBIGUOUS"
                )
                for candidate in ambiguous.resolution.candidates:
                    incoming_candidate = await view.get_relations(
                        candidate.id, direction="in", kinds=(RelationKind.CALLS,)
                    )
                    assert ambiguous in incoming_candidate.items
                statement = next(
                    e for e in batch.entities if isinstance(e, SqlStatement)
                )
                access = next(e for e in batch.entities if isinstance(e, DataAccess))
                binding = next(e for e in batch.entities if isinstance(e, SqlBinding))
                execution = next(e for e in batch.entities if isinstance(e, SqlExecute))
                assert await view.get_sql_statement(statement.id) == statement
                assert await view.get_data_access(access.id) == access
                assert await view.get_sql_binding(binding.id) == binding
                assert await view.get_sql_execute(execution.id) == execution
                caller = next(
                    e
                    for e in batch.entities
                    if isinstance(e, Symbol)
                    and e.qualified_name == "app.Service.handle"
                )
                page = await view.get_relations(
                    caller.id, kinds=(RelationKind.CALLS,), limit=1
                )
                assert (
                    page.snapshot_id == view.snapshot_id
                    and page.truncated
                    and len(page.items) == 1
                )
                rel = page.items[0]
                assert rel == catalog[rel.id]
                incoming = await view.get_relations(
                    rel.resolution.target.id,
                    direction="in",
                    kinds=(RelationKind.CALLS,),
                )
                assert rel in incoming.items
                proof = (await view.get_evidence(rel.id))[0]
                assert proof.evidence == rel.evidence[0]
                assert proof.source.provenance.snapshot_id == view.snapshot_id
                assert (
                    b"repo." in proof.source.content or b"audit" in proof.source.content
                )
                external = next(
                    e for e in batch.entities if isinstance(e, ExternalReference)
                )
                assert (await view.get_evidence(external.id))[0].source
                for invalid in ("bad", "ucm:" + "0" * 64):
                    with pytest.raises(ValueError):
                        await view.get_entity(invalid)
                for opts in (
                    {"limit": 0},
                    {"limit": True},
                    {"limit": 201},
                    {"direction": "both"},
                    {"kinds": ("WRONG",)},
                ):
                    with pytest.raises(ValueError):
                        await view.get_relations(caller.id, **opts)
                with pytest.raises(ValueError, match="SQL binding"):
                    await view.get_sql_binding(caller.id)
                with pytest.raises(ValueError, match="no Evidence"):
                    await view.get_evidence(caller.id)
                with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE ucm_entities SET name=name WHERE snapshot_id=$1",
                            view.snapshot_id,
                        )
                assert await view.get_entity(caller.id) == caller
            with pytest.raises(ValueError, match="closed"):
                await view.get_entity(caller.id)
            with pytest.raises(ValueError, match="no published snapshot"):
                async with published_reader(conn, "missing"):
                    pass
            async with conn.transaction():
                with pytest.raises(ValueError, match="free connection"):
                    async with published_reader(conn, "app"):
                        pass
        finally:
            await conn.close()

    asyncio.run(run())


def test_pinned_read_survives_publication_and_gc_without_mixing_facts(
    database_url, tmp_path
):
    async def run():
        conn = await asyncpg.connect(database_url)
        writer = await asyncpg.connect(database_url)
        try:
            await publish(conn, tmp_path)
            async with published_reader(conn, "app") as old:
                source = await conn.fetchval(
                    "SELECT entity_id FROM ucm_source_files WHERE snapshot_id=$1 AND path='Repo.java'",
                    old.snapshot_id,
                )
                old_file = await old.get_entity(source)
                sql = (await search.find_sql_executions(conn, "app"))["items"][0]
                stmt_id = sql["statements"][0]["statement_id"]
                statement = await old.get_sql_statement(stmt_id)
                assert "users" in statement.text
                (tmp_path / "Repo.java").write_text(
                    (tmp_path / "Repo.java").read_text().replace("users", "staff")
                )
                result = await index_sources(
                    writer,
                    old.repository_id,
                    tmp_path,
                    AdapterRegistry(
                        (JavaSourceAdapter(profile="orm"), GroovySourceAdapter())
                    ),
                )
                await validate_snapshot(writer, result.snapshot_id)
                await publish_snapshot(
                    writer,
                    old.repository_id,
                    result.snapshot_id,
                    expected_snapshot_id=old.snapshot_id,
                )
                await collect_garbage(writer, keep_retired=0)
                assert not await writer.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM ucm_snapshots WHERE id=$1)",
                    old.snapshot_id,
                )
                assert await old.get_entity(source) == old_file
                assert await old.get_sql_statement(stmt_id) == statement
            async with published_reader(conn, "app") as current:
                assert current.snapshot_id == result.snapshot_id
                assert (
                    await current.get_entity(source)
                ).content_sha256 != old_file.content_sha256
                assert "staff" in (await current.get_sql_statement(stmt_id)).text
        finally:
            await writer.close()
            await conn.close()

    asyncio.run(run())


def test_legacy_missing_proof_is_explicit_but_integrity_failure_is_not_hidden(
    database_url, tmp_path, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await publish(conn, tmp_path)
            async with published_reader(conn, "app") as view:
                relation = await conn.fetchval(
                    "SELECT entity_id FROM ucm_relations WHERE snapshot_id=$1 LIMIT 1",
                    view.snapshot_id,
                )

                async def unavailable(*args):
                    raise SourceUnavailableError("historical archive unavailable")

                monkeypatch.setattr(readers, "read_source_fragment", unavailable)
                proof = (await view.get_evidence(relation))[0]
                assert proof.source is None and proof.unavailable_reason

                async def corrupted(*args):
                    raise ValueError("content_sha256 mismatch")

                monkeypatch.setattr(readers, "read_source_fragment", corrupted)
                with pytest.raises(ValueError, match="content_sha256 mismatch"):
                    await view.get_evidence(relation)
        finally:
            await conn.close()

    asyncio.run(run())


def test_foreign_and_ready_only_entities_are_not_read(database_url, tmp_path):
    from code_crawler import snapshots
    from code_crawler.ucm import EntityType, logical_id

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await publish(conn, tmp_path)
            other = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="other", display_name="other", source=str(tmp_path)
                ),
            )
            registry = AdapterRegistry(
                (JavaSourceAdapter(profile="orm"), GroovySourceAdapter())
            )
            foreign = await index_sources(conn, other, tmp_path, registry)
            await validate_snapshot(conn, foreign.snapshot_id)
            await publish_snapshot(
                conn, other, foreign.snapshot_id, expected_snapshot_id=None
            )
            foreign_id = logical_id(str(other), EntityType.SOURCE_FILE, "Repo.java")
            repo = await conn.fetchval(
                "SELECT id FROM ucm_repositories WHERE repository_key='app'"
            )
            (tmp_path / "New.java").write_text("class New {}")
            from code_crawler import repos

            await repos.git("add", ".", cwd=tmp_path)
            unpublished = await index_sources(conn, repo, tmp_path, registry)
            await validate_snapshot(conn, unpublished.snapshot_id)
            new_id = logical_id(str(repo), EntityType.SOURCE_FILE, "New.java")
            async with published_reader(conn, "app") as view:
                assert view.snapshot_id != unpublished.snapshot_id
                for entity_id in (foreign_id, new_id):
                    with pytest.raises(ValueError, match="selected published snapshot"):
                        await view.get_entity(entity_id)
                    with pytest.raises(ValueError, match="selected published snapshot"):
                        await view.get_relations(entity_id)
        finally:
            await conn.close()

    asyncio.run(run())


def test_selective_incoming_plan_and_pagination(database_url, ucm_batch_factory):
    """Unrelated synthetic relations must not cause a snapshot-wide incoming scan."""
    import json

    from test_publication import create, setup

    from code_crawler.ingestion import UcmBatch
    from code_crawler.query_benchmark import RecordingConnection, plan_nodes
    from code_crawler.ucm import EntityType, Resolution, logical_id

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            base = ucm_batch_factory(repo)
            candidate = next(e for e in base.entities if isinstance(e, Relation))
            target = candidate.resolution.candidates[0]
            extra = []
            for i in range(3000):
                key = f"performance-fixture:{i}"
                data = candidate.model_dump()
                data.update(
                    id=logical_id(str(repo), EntityType.RELATION, key),
                    logical_key=key,
                    resolution=Resolution(
                        status="UNRESOLVED", reason="synthetic filler"
                    ),
                )
                extra.append(Relation.model_validate(data))
            for i in range(2):
                key = f"resolved-fixture:{i}"
                data = candidate.model_dump()
                data.update(
                    id=logical_id(str(repo), EntityType.RELATION, key),
                    logical_key=key,
                    resolution=Resolution(status="RESOLVED", target=target),
                )
                extra.append(Relation.model_validate(data))
            batch = UcmBatch(repository_id=repo, entities=(*base.entities, *extra))
            snap = await create(conn, repo, batch)
            await validate_snapshot(conn, snap)
            await publish_snapshot(conn, repo, snap, expected_snapshot_id=None)
            await conn.execute("ANALYZE")
            proxy = RecordingConnection(conn)
            async with published_reader(proxy, "repo") as view:
                expected = sorted([candidate.id, *(e.id for e in extra[-2:])])
                for _ in range(7):
                    page = await view.get_relations(
                        target.id, direction="in", kinds=("CALLS",), limit=2
                    )
                    assert [e.id for e in page.items] == expected[:2]
                    assert page.truncated
                complete = await view.get_relations(target.id, direction="in")
                assert [e.id for e in complete.items] == expected
                assert not complete.truncated
            query = next(
                q for q in proxy.queries if q.sql.startswith("SELECT r.entity_id")
            )
            plan = json.loads(
                await conn.fetchval(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query.sql,
                    *query.arguments,
                )
            )[0]
            scans = [
                n
                for n in plan_nodes(plan["Plan"])
                if n.get("Relation Name") == "ucm_relations"
            ]
            assert scans
            assert all(n["Node Type"] != "Seq Scan" for n in scans)
            assert all(n.get("Rows Removed by Filter", 0) < 100 for n in scans)
        finally:
            await conn.close()

    asyncio.run(run())
