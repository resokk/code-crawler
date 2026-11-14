import asyncio
import hashlib
import json

import asyncpg
import pytest

from code_crawler import db, discovery, jobs, publication, search, snapshots
from code_crawler.bpmn_adapter import BPMN, BpmnSourceAdapter
from code_crawler.database_schema import (
    SchemaDefinition,
    SchemaImport,
    TableDefinition,
    import_schema,
    schema_objects,
)
from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch, ingest_batch
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.openapi_adapter import OpenApiSourceAdapter
from code_crawler.publication import (
    publish_snapshot,
    rollback_publication,
    validate_snapshot,
)
from code_crawler.search_storage import read_search_documents, rebuild_search_documents
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.source_evidence import archive_sources
from code_crawler.ucm import DatabaseObject, EntityType, SourceFile, logical_id

pytestmark = pytest.mark.integration


async def migrate(conn):
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")


async def repository(conn, key):
    return await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key=key, display_name=key, source="fixture"
        ),
    )


def source(repo, path, text, language):
    content = text.encode()
    file = SourceFile(
        repository_id=str(repo),
        logical_key=path,
        id=logical_id(str(repo), EntityType.SOURCE_FILE, path),
        name=path,
        path=path,
        language=language,
        content_sha256=hashlib.sha256(content).hexdigest(),
    )
    return SourceInput(file, content)


async def snapshot(
    conn,
    repo,
    *,
    java="package app; class A { void run(int x) {} void run(String x) {} void order(int a, String b) {} void order(String a, int b) {} }",
    xml=None,
    schemas=(),
    api=None,
):
    sources = [source(repo, "A.java", java, "java")]
    if xml:
        sources.append(source(repo, "p.bpmn", xml, "bpmn"))
    if api:
        sources.append(source(repo, "api.json", json.dumps(api), "openapi"))
    registry = AdapterRegistry(
        (
            JavaSourceAdapter(profile="symbols"),
            BpmnSourceAdapter(),
            OpenApiSourceAdapter(),
        )
    )
    prepared = await registry.prepare(tuple(sources))
    facts = [e for f in await prepared(tuple(sources)) for e in f.entities]
    for i, schema in enumerate(schemas):
        await import_schema(conn, schema)
        file = source(repo, f"schema{i}.json", "{}", "unknown")
        sources.append(file)
        for obj in schema_objects(schema):
            key = json.dumps(
                ["database.object", file.file.id, obj.object_key], separators=(",", ":")
            )
            facts.append(
                DatabaseObject(
                    repository_id=str(repo),
                    logical_key=key,
                    id=logical_id(str(repo), EntityType.DATABASE_OBJECT, key),
                    name=obj.table_name or obj.schema_name,
                    projection_file_id=file.file.id,
                    database_key=schema.database_key,
                    version_key=schema.version_key,
                    schema_fingerprint=schema.fingerprint,
                    object_key=obj.object_key,
                    object_kind=obj.object_kind,
                    catalog_name=schema.catalog_name,
                    schema_name=obj.schema_name,
                    table_name=obj.table_name,
                    column_name=obj.column_name,
                )
            )
    sid = await snapshots.create_snapshot(
        conn,
        repo,
        snapshots.SnapshotInput(
            commit_hash="fixture", source_fingerprint="a" * 64, dirty=False
        ),
    )
    await ingest_batch(
        conn,
        sid,
        UcmBatch(repository_id=repo, entities=(*(s.file for s in sources), *facts)),
    )
    await archive_sources(conn, sid, tuple(sources), origin="PROVIDED_BYTES")
    return sid


async def publish(conn, repo, sid, previous=None):
    await validate_snapshot(conn, sid)
    await publish_snapshot(conn, repo, sid, expected_snapshot_id=previous)


async def lookup(conn, key="app.A.run", **options):
    return await search.search_discovery_entries(
        conn, "SYMBOL", key, allowed_repository_keys=["one", "two"], **options
    )


def test_ambiguity_published_only_scope_signature_and_partial_availability(
    database_url,
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            one, two = await repository(conn, "one"), await repository(conn, "two")
            a, b = await snapshot(conn, one), await snapshot(conn, two)
            empty = await lookup(conn)
            assert empty["items"] == [] and empty["availability"] == "PARTIAL"
            async with conn.transaction():
                with pytest.raises(ValueError, match="published"):
                    await discovery.build_generation(conn, a)
            await publish(conn, one, a)
            first = await lookup(conn, qualifier={"parameter_types": ["int"]})
            assert len(first["items"]) == 1 and first["resolution"] == "UNRESOLVED"
            assert first["availability"] == "PARTIAL"
            assert first["items"][0]["snapshot_id"] == str(a)
            for mutation in (
                "UPDATE search_discovery_entries SET lookup_key=jsonb_build_array('fabricated')",
                "DELETE FROM search_discovery_entries",
                "UPDATE search_discovery_generations SET state='BUILDING'",
                "TRUNCATE search_discovery_entries",
            ):
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(mutation)
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO search_discovery_entries(snapshot_id,generation,repository_id,entity_id,entity_type,kind,lookup_key,qualifier,rule) SELECT snapshot_id,generation,repository_id,entity_id,entity_type,'DATABASE',lookup_key,qualifier,rule FROM search_discovery_entries LIMIT 1"
                )

            await publish(conn, two, b)
            both = await lookup(conn, qualifier={"parameter_types": ["int"]})
            assert len(both["items"]) == 2 and both["resolution"] == "AMBIGUOUS"
            assert both["availability"] == "COMPLETE"
            assert all(
                i["certainty"] == "UNKNOWN" and i["resolution"] == "UNRESOLVED"
                for i in both["items"]
            )
            assert len((await lookup(conn))["items"]) == 4
            ordered = await lookup(
                conn,
                key="app.A.order",
                qualifier={"parameter_types": ["String", "int"]},
            )
            assert len(ordered["items"]) == 2
            assert all(
                i["qualifier"]["parameter_types"] == ["String", "int"]
                for i in ordered["items"]
            )
            assert not (await lookup(conn, key="APP.A.run"))["items"]
            assert not (await lookup(conn, qualifier={"parameter_types": []}))["items"]
            assert len((await lookup(conn, repository_keys=["one"]))["items"]) == 2
            with pytest.raises(ValueError, match="access denied"):
                await search.search_discovery_entries(
                    conn,
                    "SYMBOL",
                    "app.A",
                    allowed_repository_keys=["one"],
                    repository_keys=["two"],
                )
            assert not await conn.fetchval(
                "SELECT count(*) FROM ucm_relations WHERE relation_kind='EXTERNAL_DEPENDENCY'"
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_atomic_failure_rollback_refresh_generation_and_gc(database_url, monkeypatch):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            one, two = await repository(conn, "one"), await repository(conn, "two")
            old = await snapshot(conn, one)
            unrelated = await snapshot(conn, two)
            await publish(conn, one, old)
            await publish(conn, two, unrelated)
            before = await lookup(conn)
            await rebuild_search_documents(
                conn,
                one,
                old,
                allowed_repository_ids=(one,),
                policy_version="fixture",
                redact=lambda value: value,
                expected_generation_id=None,
            )
            assert await lookup(conn) == before
            new = await snapshot(
                conn, one, java="package app; class A { void newer() {} }"
            )
            await validate_snapshot(conn, new)
            await rebuild_search_documents(
                conn,
                one,
                new,
                allowed_repository_ids=(one,),
                policy_version="fixture",
                redact=lambda value: value,
                expected_generation_id=None,
            )
            original = publication.build_generation

            async def fail(*args):
                await original(*args)
                raise RuntimeError("projector failure")

            monkeypatch.setattr(publication, "build_generation", fail)
            with pytest.raises(RuntimeError, match="projector failure"):
                await publish_snapshot(conn, one, new, expected_snapshot_id=old)
            assert (await lookup(conn)) == before
            assert (
                await conn.fetchval("SELECT state FROM ucm_snapshots WHERE id=$1", new)
                == "READY"
            )
            assert not await conn.fetchval(
                "SELECT count(*) FROM search_discovery_generations WHERE snapshot_id=$1",
                new,
            )
            monkeypatch.setattr(publication, "build_generation", original)
            await publish_snapshot(conn, one, new, expected_snapshot_id=old)
            changed = await lookup(conn)
            assert len(changed["items"]) == 2
            assert changed["fingerprint"] != before["fingerprint"]
            assert changed["generation_manifest"][1] == before["generation_manifest"][1]
            await rollback_publication(conn, one, old, expected_snapshot_id=new)
            assert await lookup(conn) == before
            documents = await read_search_documents(
                conn, one, allowed_repository_ids=(one,)
            )
            assert documents and all(d["snapshot_id"] == old for d in documents)
            generation = await discovery.refresh_discovery(conn, "one")
            assert str(generation) == before["generation_manifest"][0]["generation_id"]
            monkeypatch.setattr(discovery, "VERSION", "discovery/test-next")
            generation2 = await discovery.refresh_discovery(conn, "one")
            assert generation2 != generation
            unavailable = await lookup(conn)
            # One repository still has v1, so version-skew is explicit.
            assert unavailable["availability"] == "PARTIAL"
            monkeypatch.setattr(discovery, "VERSION", "discovery/2")
            await discovery.refresh_discovery(conn, "one")
            await jobs.collect_garbage(conn, keep_retired=0)
            assert not await conn.fetchval(
                "SELECT count(*) FROM search_discovery_generations WHERE snapshot_id=$1",
                new,
            )
            assert await lookup(conn) == before
        finally:
            await conn.close()

    asyncio.run(run())


def test_bpmn_namespace_precision_and_unknown_target_types(database_url):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            for key, namespace in [("one", "urn:one"), ("two", "urn:two")]:
                repo = await repository(conn, key)
                sid = await snapshot(
                    conn,
                    repo,
                    xml=f'<definitions xmlns="{BPMN}" xmlns:c="http://camunda.org/schema/1.0/bpmn" targetNamespace="{namespace}"><process id="payments"><serviceTask id="t" c:topic="worker"/></process></definitions>',
                )
                await publish(conn, repo, sid)
            result = await search.search_discovery_entries(
                conn, "BPMN_PROCESS", "payments", allowed_repository_keys=["one", "two"]
            )
            assert len(result["items"]) == 2
            selected = await search.search_discovery_entries(
                conn,
                "BPMN_PROCESS",
                "payments",
                allowed_repository_keys=["one", "two"],
                qualifier={"target_namespace": "urn:one"},
            )
            assert (
                len(selected["items"]) == 1
                and selected["items"][0]["repository_key"] == "one"
            )
            for kind, qualifier in [
                ("BPMN_WORKER", {}),
                ("HTTP", {"service": "billing", "method": "GET"}),
                ("KAFKA", {"cluster": "prod"}),
                ("REFERENCE_DATA", {"namespace": "org"}),
            ]:
                unsupported = await search.search_discovery_entries(
                    conn,
                    kind,
                    "worker",
                    allowed_repository_keys=["one", "two"],
                    qualifier=qualifier,
                )
                assert unsupported["coverage"]["status"] == (
                    "PARTIAL" if kind == "HTTP" else "UNSUPPORTED"
                )
                assert not unsupported["items"]
        finally:
            await conn.close()

    asyncio.run(run())


def test_database_contexts_do_not_collapse_identifiers(database_url):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            repo = await repository(conn, "one")
            schemas = tuple(
                SchemaImport(
                    database_key=key,
                    version_key="v1",
                    dialect="postgres",
                    catalog_name="app",
                    schemas=(
                        SchemaDefinition(
                            name="public", tables=(TableDefinition(name="Users"),)
                        ),
                    ),
                )
                for key in ("prod", "test")
            )
            sid = await snapshot(conn, repo, schemas=schemas)
            await publish(conn, repo, sid)
            for key in ("prod", "test"):
                result = await search.search_discovery_entries(
                    conn,
                    "DATABASE",
                    "Users",
                    allowed_repository_keys=["one"],
                    qualifier={
                        "database_key": key,
                        "version_key": "v1",
                        "catalog_name": "app",
                        "schema_name": "public",
                    },
                )
                assert len(result["items"]) == 1
                assert result["items"][0]["qualifier"]["database_key"] == key
            result = await search.search_discovery_entries(
                conn,
                "DATABASE",
                "users",
                allowed_repository_keys=["one"],
                qualifier={
                    "database_key": "prod",
                    "version_key": "v1",
                    "catalog_name": "app",
                    "schema_name": "public",
                },
            )
            assert not result["items"]
        finally:
            await conn.close()

    asyncio.run(run())


def test_pagination_mvcc_and_existing_publication_refresh(database_url):
    async def run():
        conn = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            one, two = await repository(conn, "one"), await repository(conn, "two")
            old = await snapshot(conn, one)
            await publish(conn, one, old)
            await publish(conn, two, await snapshot(conn, two))
            first = await lookup(conn, limit=1)
            second = await lookup(
                conn, limit=1, offset=1, expected_fingerprint=first["fingerprint"]
            )
            assert first["items"][0]["entity_id"] != second["items"][0]["entity_id"]
            assert first["truncated"]
            new = await snapshot(
                other, one, java="package app; class A { void run() {} }"
            )
            await validate_snapshot(other, new)
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                pinned = await lookup(conn)
                await publish_snapshot(other, one, new, expected_snapshot_id=old)
                assert await lookup(conn) == pinned
            with pytest.raises(ValueError, match="generation changed"):
                await lookup(
                    conn, limit=1, offset=1, expected_fingerprint=first["fingerprint"]
                )
            # Simulate an existing pre-migration publication with no derivative pointer.
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('code_crawler.discovery_build','on',true)"
                )
                await conn.execute(
                    "DELETE FROM search_discovery_generations WHERE snapshot_id=$1", new
                )
            assert (await lookup(conn))["availability"] == "PARTIAL"
            await discovery.refresh_discovery(conn, "one")
            assert (await lookup(conn))["availability"] == "COMPLETE"
        finally:
            await conn.close()
            await other.close()

    asyncio.run(run())


def test_openapi_contract_namespace_is_not_a_runtime_service_binding(database_url):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            api = {
                "openapi": "3.1.0",
                "info": {"title": "billing", "version": "1"},
                "paths": {
                    "/orders": {"get": {"responses": {"200": {"description": "ok"}}}}
                },
                "webhooks": {
                    "/orders": {"get": {"responses": {"200": {"description": "hook"}}}}
                },
            }
            roots = []
            for key in ("one", "two"):
                repo = await repository(conn, key)
                sid = await snapshot(conn, repo, api=api)
                await publish(conn, repo, sid)
                root = await conn.fetchval(
                    "SELECT entity_id FROM ucm_symbols WHERE snapshot_id=$1 AND symbol_kind='OPENAPI_DOCUMENT'",
                    sid,
                )
                roots.append(root)
            selected = await search.search_discovery_entries(
                conn,
                "HTTP",
                "/orders",
                allowed_repository_keys=["one", "two"],
                qualifier={"contract_id": roots[0], "method": "GET"},
            )
            assert len(selected["items"]) == 1
            assert selected["items"][0]["repository_key"] == "one"
            assert selected["items"][0]["qualifier"]["service"] is None
            assert selected["coverage"]["status"] == "PARTIAL"
            assert selected["resolution"] == "UNRESOLVED"
            assert selected["items"][0]["certainty"] == "UNKNOWN"
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM search_discovery_entries WHERE kind='HTTP'"
                )
                == 2
            )
            unknown = await search.search_discovery_entries(
                conn,
                "HTTP",
                "/orders",
                allowed_repository_keys=["one", "two"],
                qualifier={"service": "billing", "method": "GET"},
            )
            assert not unknown["items"]
            exact = await discovery.lookup(
                conn,
                "HTTP",
                (None, "GET", "/orders", roots[0]),
                repository_keys=("one",),
                allowed_repositories=frozenset({"one"}),
            )
            assert len(exact["items"]) == 1
        finally:
            await conn.close()

    asyncio.run(run())
