import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from test_jpa_orm_storage import setup as setup_orm
from test_publication import create, setup

from code_crawler import publication, snapshots
from code_crawler.database_schema import SchemaImport, import_schema
from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch, ingest_stream
from code_crawler.java_lineage import JavaLineageAnalyzer
from code_crawler.java_orm import index_java_orm
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.source_evidence import archive_sources
from code_crawler.ucm import (
    DataAccess,
    DatabaseAccess,
    DatabaseContext,
    Entity,
    EntityRef,
    EntityType,
    Operation,
    Relation,
    RelationKind,
    Resolution,
    Scope,
    SourceFile,
    SqlBinding,
    SqlConstruction,
    SqlPlaceholder,
    SqlStatement,
    Value,
    logical_id,
)
from code_crawler.validation_benchmark import SOURCE, benchmark, sql_chunks, sql_fixture

pytestmark = pytest.mark.integration


async def fixture(conn: asyncpg.Connection, repo: UUID) -> tuple[UcmBatch, SourceInput]:
    text = b"""import java.sql.Connection; import java.sql.PreparedStatement;
import java.util.Map; import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
class A {void m(Connection c,int id,NamedParameterJdbcTemplate j,boolean flag){
PreparedStatement a=c.prepareStatement("select id from users where id=?"); a.setInt(1,id); a.execute();
PreparedStatement b=c.prepareStatement("delete from users where id=?"); b.setInt(1,id); b.execute();
j.update("delete from users where id=:id",Map.of("id",id));
String sql=flag?"select id from a":"select id from b"; j.update(sql,Map.of());
j.update("select * from ; delete from t",Map.of());
}}"""
    file = SourceFile(
        repository_id=str(repo),
        logical_key="A.java",
        name="A.java",
        path="A.java",
        language="java",
        content_sha256=hashlib.sha256(text).hexdigest(),
        id=logical_id(str(repo), EntityType.SOURCE_FILE, "A.java"),
    )
    source = SourceInput(file, text)
    results = await JavaLineageAnalyzer((source,))((source,))
    entities = [file, *results[0].entities]
    document = SchemaImport(
        database_key="db",
        version_key="v1",
        dialect="postgres",
        catalog_name="app",
        schemas=(),
    )
    await import_schema(conn, document)
    contexts = []
    for connection in ("one", "two"):
        key = json.dumps(
            ["database.context", file.id, connection, "db", "v1", []],
            separators=(",", ":"),
        )
        contexts.append(
            DatabaseContext(
                repository_id=str(repo),
                logical_key=key,
                name=connection,
                id=logical_id(str(repo), EntityType.DATABASE_CONTEXT, key),
                projection_file_id=file.id,
                connection_key=connection,
                database_key="db",
                version_key="v1",
                schema_fingerprint=document.fingerprint,
            )
        )
    execution = next(
        e
        for e in entities
        if isinstance(e, Relation)
        and e.relation_kind == RelationKind.EXECUTES_STATEMENT
        and e.resolution.status == "RESOLVED"
    )
    access = next(
        e
        for e in entities
        if isinstance(e, DataAccess)
        and e.statement_id == execution.resolution.target.id
    )
    key = "context-access"
    contextual = DatabaseAccess(
        repository_id=str(repo),
        logical_key=key,
        name=key,
        id=logical_id(str(repo), EntityType.DATABASE_ACCESS, key),
        access_id=access.id,
        execution_id=execution.source.id,
        context_id=contexts[0].id,
    )
    key = "context-usage"
    usage = Relation(
        repository_id=str(repo),
        logical_key=key,
        name=key,
        id=logical_id(str(repo), EntityType.RELATION, key),
        relation_kind=RelationKind.USES_DATABASE_CONTEXT,
        source=execution.source,
        resolution=Resolution(
            status="RESOLVED",
            target=EntityRef(
                id=contexts[0].id, entity_type=EntityType.DATABASE_CONTEXT
            ),
        ),
        certainty=execution.certainty,
        evidence=execution.evidence,
        coverage=execution.coverage,
    )
    return UcmBatch(
        repository_id=repo, entities=(*entities, *contexts, contextual, usage)
    ), source


def mutate(batch: UcmBatch, problem: str) -> tuple[Entity, ...]:
    entities = list(batch.entities)

    def change(entity: Entity, **updates: object) -> None:
        entities[entities.index(entity)] = entity.model_copy(update=updates)

    executions = [
        e
        for e in entities
        if isinstance(e, Relation)
        and e.relation_kind == RelationKind.EXECUTES_STATEMENT
        and e.resolution.status == "RESOLVED"
    ]
    if problem == "statement_slice":
        statement = next(e for e in entities if isinstance(e, SqlStatement))
        change(statement, text="X" + statement.text[1:])
    elif problem in ("partial_complete", "partial_access"):
        construction = next(
            e
            for e in entities
            if isinstance(e, SqlConstruction)
            and any(
                isinstance(s, SqlStatement)
                and s.candidate_id == e.variants[0].candidate_id
                and s.parse_status == "COMPLETE"
                for s in entities
            )
        )
        change(
            construction,
            variants=(
                construction.variants[0].model_copy(
                    update={
                        "partial": True,
                        "partial_reasons": ("synthetic uncertainty",),
                    }
                ),
            ),
        )
        if problem == "partial_access":
            for s in tuple(entities):
                if (
                    isinstance(s, SqlStatement)
                    and s.candidate_id == construction.variants[0].candidate_id
                ):
                    change(
                        s, parse_status="PARTIAL", reasons=("synthetic uncertainty",)
                    )
            # Partial execution relations are required independently of access rejection.
            for e in executions:
                if any(
                    isinstance(s, SqlStatement)
                    and s.id == e.resolution.target.id
                    and s.candidate_id == construction.variants[0].candidate_id
                    for s in entities
                ):
                    change(
                        e,
                        resolution=Resolution(
                            status="PARTIAL",
                            candidates=(e.resolution.target,),
                            reason="partial",
                        ),
                    )
    elif problem == "execution_origin":
        statements = {e.id: e for e in entities if isinstance(e, SqlStatement)}
        other = next(
            e
            for e in executions
            if statements[e.resolution.target.id].candidate_id
            != statements[executions[0].resolution.target.id].candidate_id
        )
        change(executions[0], resolution=other.resolution)
    elif problem in ("multiple_variants_definite", "failed_statement_definite"):
        statements = {e.id: e for e in entities if isinstance(e, SqlStatement)}
        relation = next(
            e
            for e in entities
            if isinstance(e, Relation)
            and e.relation_kind == RelationKind.EXECUTES_STATEMENT
            and e.resolution.status == "PARTIAL"
            and e.resolution.candidates
            and (statements[e.resolution.candidates[0].id].parse_status == "COMPLETE")
            == (problem == "multiple_variants_definite")
        )
        change(
            relation,
            resolution=Resolution(
                status="RESOLVED", target=relation.resolution.candidates[0]
            ),
        )
    elif problem in ("ambiguous_definite", "duplicate_usage"):
        usage = next(
            e
            for e in entities
            if isinstance(e, Relation)
            and e.relation_kind == RelationKind.USES_SQL_CONSTRUCTION
            and e.source.id == executions[0].source.id
        )
        if problem == "ambiguous_definite":
            change(
                usage,
                resolution=Resolution(
                    status="PARTIAL",
                    candidates=(usage.resolution.target,),
                    reason="uncertain",
                ),
            )
        else:
            key = "duplicate-usage"
            entities.append(
                usage.model_copy(
                    update={
                        "logical_key": key,
                        "id": logical_id(
                            str(batch.repository_id), EntityType.RELATION, key
                        ),
                    }
                )
            )
    elif problem in ("binding_position", "binding_name"):
        parameter = next(
            e
            for e in entities
            if isinstance(e, SqlPlaceholder)
            and e.parameter_kind
            == ("POSITIONAL" if problem == "binding_position" else "NAMED")
        )
        change(
            parameter,
            **(
                {"position": 99}
                if problem == "binding_position"
                else {"parameter_name": "wrong"}
            ),
        )
    elif problem == "binding_membership":
        relation = next(
            e
            for e in entities
            if isinstance(e, Relation)
            and e.relation_kind == RelationKind.BINDS_PARAMETER
            and e.resolution.status == "RESOLVED"
        )
        parameter = next(
            e
            for e in entities
            if isinstance(e, SqlPlaceholder)
            and e.statement_id
            != next(
                p.statement_id
                for p in entities
                if isinstance(p, SqlPlaceholder)
                and p.id == relation.resolution.target.id
            )
        )
        change(
            relation,
            resolution=Resolution(
                status="RESOLVED",
                target=EntityRef(
                    id=parameter.id, entity_type=EntityType.SQL_PLACEHOLDER
                ),
            ),
        )
    elif problem == "incomplete_binding":
        binding = next(
            e for e in entities if isinstance(e, SqlBinding) and e.status == "BOUND"
        )
        change(binding, status="PARTIAL", reasons=("uncertain",))
    elif problem in ("database_statement", "database_context"):
        access = next(e for e in entities if isinstance(e, DatabaseAccess))
        if problem == "database_statement":
            change(
                access,
                execution_id=next(
                    e.source.id
                    for e in executions
                    if e.source.id != access.execution_id
                ),
            )
        else:
            change(
                access,
                context_id=next(
                    e.id
                    for e in entities
                    if isinstance(e, DatabaseContext) and e.id != access.context_id
                ),
            )
    elif problem == "duplicate_producer":
        operation = next(e for e in entities if isinstance(e, Operation))
        value = next(
            e
            for e in entities
            if isinstance(e, Value) and e.id not in operation.input_value_ids
        )
        for n in range(2):
            key = f"duplicate-producer:{n}"
            entities.append(
                operation.model_copy(
                    update={
                        "logical_key": key,
                        "id": logical_id(
                            str(batch.repository_id), EntityType.OPERATION, key
                        ),
                        "output_value_ids": (value.id,),
                    }
                )
            )
    return tuple(entities)


@pytest.mark.parametrize(
    "problem",
    [
        "valid",
        "statement_slice",
        "partial_complete",
        "partial_access",
        "execution_origin",
        "multiple_variants_definite",
        "failed_statement_definite",
        "ambiguous_definite",
        "duplicate_usage",
        "binding_position",
        "binding_name",
        "binding_membership",
        "incomplete_binding",
        "database_statement",
        "database_context",
        "duplicate_producer",
    ],
)
def test_sql_readiness_matches_whole_batch(
    database_url: str, problem: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publication, "_SLICE", 7)
    monkeypatch.setattr(publication, "_CACHE", 3)
    original_fetch = publication._fetch

    async def bounded_fetch(conn, snapshot, ids):
        assert len(ids) <= publication._SLICE
        return await original_fetch(conn, snapshot, ids)

    monkeypatch.setattr(publication, "_fetch", bounded_fetch)

    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            previous = await create(conn, repo)
            await validate_snapshot(conn, previous)
            await publish_snapshot(conn, repo, previous, expected_snapshot_id=None)
            batch, source = await fixture(conn, repo)
            entities = mutate(batch, problem)
            if problem != "valid":
                with pytest.raises(ValueError):
                    UcmBatch(repository_id=repo, entities=entities)
            snapshot = await create(conn, repo)

            async def chunks() -> AsyncIterator[tuple[Entity, ...]]:
                for start in range(0, len(entities), 11):
                    yield entities[start : start + 11]

            await ingest_stream(conn, snapshot, repo, chunks())
            await archive_sources(conn, snapshot, (source,), origin="PROVIDED_BYTES")
            if problem == "valid":
                assert await validate_snapshot(conn, snapshot) == len(entities)
                assert {
                    e.id: e
                    for e in (await load_snapshot_batch(conn, snapshot)).entities
                } == {e.id: e for e in entities}
            else:
                with pytest.raises(ValueError):
                    await validate_snapshot(conn, snapshot)
                with pytest.raises(ValueError):
                    await load_snapshot_batch(conn, snapshot)
                assert not await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM ucm_snapshot_validations WHERE snapshot_id=$1)",
                    snapshot,
                )
                assert (
                    await conn.fetchval(
                        "SELECT state FROM ucm_snapshots WHERE id=$1", snapshot
                    )
                    == "VALIDATING"
                )
                assert (await snapshots.published_snapshot(conn, repo))[
                    "id"
                ] == previous
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_class WHERE relnamespace=pg_my_temp_schema() AND relname LIKE 'validation_%')"
            )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_sql_dense_memory_is_bounded(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publication, "_SLICE", 64)
    monkeypatch.setattr(publication, "_CACHE", 128)

    async def scenario() -> None:
        small = await benchmark(database_url, 250)
        large = await benchmark(database_url, 1000)
        assert large["entities"] > small["entities"] * 3.9
        assert large["peak_python_bytes"] < small["peak_python_bytes"] * 1.5, (
            small,
            large,
        )

    asyncio.run(scenario())


@pytest.mark.parametrize("cycle", [False, True])
def test_scope_pointer_jumping_handles_deep_chains(
    database_url: str, cycle: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publication, "_SLICE", 31)
    monkeypatch.setattr(publication, "_CACHE", 7)
    original_catalog = publication._Catalog

    class BoundedCatalog(original_catalog):
        def __getitem__(self, key):
            assert len(self.entities) <= 7
            result = super().__getitem__(key)
            assert len(self.entities) <= 7
            return result

    monkeypatch.setattr(publication, "_Catalog", BoundedCatalog)

    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            count = 1500

            def scope_id(index: int) -> str:
                return logical_id(str(repo), EntityType.SCOPE, f"scope:{index}")

            scopes = tuple(
                Scope(
                    repository_id=str(repo),
                    logical_key=f"scope:{i}",
                    name=f"s{i}",
                    id=scope_id(i),
                    scope_kind="BLOCK",
                    parent_scope_id=scope_id(i + 1)
                    if i + 1 < count
                    else (scope_id(0) if cycle else None),
                )
                for i in range(count)
            )
            if cycle:
                with pytest.raises(ValueError, match="cyclic"):
                    UcmBatch(repository_id=repo, entities=scopes)
            else:
                UcmBatch(repository_id=repo, entities=scopes)
            snapshot = await create(conn, repo)

            async def chunks():
                yield scopes

            await ingest_stream(conn, snapshot, repo, chunks())
            if cycle:
                with pytest.raises(ValueError, match="cyclic"):
                    await validate_snapshot(conn, snapshot)
            else:
                assert await validate_snapshot(conn, snapshot) == count
        finally:
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("action", ["cancel", "ready", "publish"])
def test_validation_lease_receipt_and_concurrent_state(
    database_url: str,
    ucm_batch_factory: Callable[[UUID], UcmBatch],
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    async def scenario() -> None:
        writer = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        task = None
        reached, release = asyncio.Event(), asyncio.Event()
        original = publication.check_sql_semantics

        async def paused(conn, snapshot):
            await original(conn, snapshot)
            if conn is writer:
                reached.set()
                await release.wait()

        try:
            repo = await setup(writer)
            batch = ucm_batch_factory(repo)
            previous = await create(writer, repo, batch)
            await validate_snapshot(writer, previous)
            await publish_snapshot(writer, repo, previous, expected_snapshot_id=None)
            snapshot = await create(writer, repo, batch)
            monkeypatch.setattr(publication, "check_sql_semantics", paused)
            task = asyncio.create_task(validate_snapshot(writer, snapshot))
            await asyncio.wait_for(reached.wait(), timeout=10)
            async with other.transaction():
                assert not await other.fetchval(
                    snapshots._TRY_GC_LEASE, snapshots._SNAPSHOT_LOCK, str(snapshot)
                )
            assert not await other.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_snapshot_validations WHERE snapshot_id=$1)",
                snapshot,
            )
            if action == "cancel":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert not writer.is_in_transaction()
                assert not await writer.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM pg_class WHERE relnamespace=pg_my_temp_schema() AND relname LIKE 'validation_%')"
                )
                async with other.transaction():
                    assert await other.fetchval(
                        snapshots._TRY_GC_LEASE, snapshots._SNAPSHOT_LOCK, str(snapshot)
                    )
                assert (await snapshots.published_snapshot(other, repo))[
                    "id"
                ] == previous
                assert not await other.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM ucm_snapshot_validations WHERE snapshot_id=$1)",
                    snapshot,
                )
                monkeypatch.setattr(publication, "check_sql_semantics", original)
                assert await validate_snapshot(writer, snapshot) == len(batch.entities)
            else:
                assert await validate_snapshot(other, snapshot) == len(batch.entities)
                receipt = await other.fetchrow(
                    "SELECT * FROM ucm_snapshot_validations WHERE snapshot_id=$1",
                    snapshot,
                )
                if action == "publish":
                    await publish_snapshot(
                        other, repo, snapshot, expected_snapshot_id=previous
                    )
                release.set()
                if action == "publish":
                    with pytest.raises(ValueError, match="state changed"):
                        await task
                else:
                    assert await task == len(batch.entities)
                assert (
                    await other.fetchrow(
                        "SELECT * FROM ucm_snapshot_validations WHERE snapshot_id=$1",
                        snapshot,
                    )
                    == receipt
                )
        finally:
            release.set()
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await writer.close()
            await other.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "problem", ["invocation_owner", "attribute_owner", "named_query"]
)
def test_orm_corruption_matches_reference_validator(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, problem: str
) -> None:
    monkeypatch.setattr(publication, "_SLICE", 5)
    monkeypatch.setattr(publication, "_CACHE", 2)

    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, assignments = await setup_orm(conn, tmp_path)
            result = await index_java_orm(conn, repo, tmp_path, assignments)
            snapshot = result.snapshot_id
            if problem == "invocation_owner":
                owner = await conn.fetchval(
                    "SELECT entity_id FROM ucm_symbols WHERE snapshot_id=$1 AND symbol_kind='CLASS' LIMIT 1",
                    snapshot,
                )
                await conn.execute(
                    "UPDATE ucm_orm_operations SET owner_symbol_id=$2 WHERE snapshot_id=$1",
                    snapshot,
                    owner,
                )
            elif problem == "attribute_owner":
                owner = await conn.fetchval(
                    "SELECT entity_id FROM ucm_symbols WHERE snapshot_id=$1 AND qualified_name='Dao'",
                    snapshot,
                )
                assert owner is not None
                await conn.execute(
                    "UPDATE ucm_orm_mappings SET owner_symbol_id=$2 WHERE snapshot_id=$1 AND mapping_kind='ATTRIBUTE'",
                    snapshot,
                    owner,
                )
            else:
                target = await conn.fetchval(
                    "SELECT target_id FROM ucm_relations WHERE snapshot_id=$1 AND relation_kind='ORM_NAMED_QUERY' AND target_id IS NOT NULL LIMIT 1",
                    snapshot,
                )
                assert target is not None
                await conn.execute(
                    "UPDATE ucm_orm_queries SET query_name='Different' WHERE snapshot_id=$1 AND entity_id=$2",
                    snapshot,
                    target,
                )
            with pytest.raises(ValueError):
                await validate_snapshot(conn, snapshot)
            with pytest.raises(ValueError):
                await load_snapshot_batch(conn, snapshot)
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_snapshot_validations WHERE snapshot_id=$1)",
                snapshot,
            )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_cancellation_drains_worker_reference_reads(
    database_url: str,
    ucm_batch_factory: Callable[[UUID], UcmBatch],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(publication, "_SLICE", 1)
    monkeypatch.setattr(publication, "_CACHE", 1)

    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        original = publication._fetch
        reached, release = asyncio.Event(), asyncio.Event()
        task = None

        async def delayed(connection, snapshot, ids):
            if asyncio.current_task() is not task:
                reached.set()
                await release.wait()
            return await original(connection, snapshot, ids)

        try:
            repo = await setup(conn)
            batch = ucm_batch_factory(repo)
            snapshot = await create(conn, repo, batch)
            monkeypatch.setattr(publication, "_fetch", delayed)
            task = asyncio.create_task(validate_snapshot(conn, snapshot))
            await asyncio.wait_for(reached.wait(), timeout=10)
            task.cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not task.done()
            assert conn.is_in_transaction()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=10)
            assert not conn.is_in_transaction()
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_snapshot_validations WHERE snapshot_id=$1)",
                snapshot,
            )
            monkeypatch.setattr(publication, "_fetch", original)
            assert await validate_snapshot(conn, snapshot) == len(batch.entities)
        finally:
            release.set()
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("problem", ["partial_complete", "partial_access"])
def test_partial_construction_global_rule_without_placeholders(
    database_url: str, problem: str
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            entities = [*sql_fixture(repo), *sql_fixture(repo, 0)]
            for index, entity in enumerate(entities):
                if isinstance(entity, SqlConstruction):
                    entities[index] = entity.model_copy(
                        update={
                            "variants": (
                                entity.variants[0].model_copy(
                                    update={
                                        "partial": True,
                                        "partial_reasons": ("partial",),
                                    }
                                ),
                            )
                        }
                    )
                elif isinstance(entity, SqlStatement) and problem == "partial_access":
                    entities[index] = entity.model_copy(
                        update={"parse_status": "PARTIAL", "reasons": ("partial",)}
                    )
            message = "partial SQL construction cannot assert " + (
                "accesses" if problem == "partial_access" else "complete semantics"
            )
            with pytest.raises(ValueError, match=message):
                UcmBatch(repository_id=repo, entities=tuple(entities))
            snapshot = await create(conn, repo)

            async def chunks():
                yield tuple(entities)

            await ingest_stream(conn, snapshot, repo, chunks())
            await archive_sources(
                conn,
                snapshot,
                (SourceInput(entities[0], SOURCE),),
                origin="PROVIDED_BYTES",
            )
            with pytest.raises(ValueError, match=message):
                await validate_snapshot(conn, snapshot)
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_prefetch_does_not_evict_the_current_slices_cache_hits(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publication, "_SLICE", 31)
    monkeypatch.setattr(publication, "_CACHE", 200)
    original = publication._Catalog
    misses = []

    class ObservedCatalog(original):
        def __getitem__(self, key):
            if key is not None and key not in self.entities:
                misses.append(key)
            return super().__getitem__(key)

    monkeypatch.setattr(publication, "_Catalog", ObservedCatalog)

    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            snapshot = await create(conn, repo)
            await ingest_stream(conn, snapshot, repo, sql_chunks(repo, 500))
            await archive_sources(
                conn,
                snapshot,
                (SourceInput(sql_fixture(repo)[0], SOURCE),),
                origin="PROVIDED_BYTES",
            )
            assert await validate_snapshot(conn, snapshot) == 2002
            # All direct references fit the fixed cache; no N+1 reads are needed.
            assert not misses
        finally:
            await conn.close()

    asyncio.run(scenario())
