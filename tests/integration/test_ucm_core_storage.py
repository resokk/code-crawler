import asyncio
from uuid import UUID

import asyncpg
import pytest

from code_crawler import db, snapshots
from code_crawler.ucm import EntityType, logical_id, relation_registry

pytestmark = pytest.mark.integration


async def insert(conn: asyncpg.Connection, table: str, **fields: object) -> None:
    placeholders = ",".join(f"${i}" for i in range(1, len(fields) + 1))
    await conn.execute(
        f"INSERT INTO public.{table} ({','.join(fields)}) VALUES ({placeholders})",
        *fields.values(),
    )


async def setup(conn: asyncpg.Connection) -> tuple[UUID, UUID]:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    repo = await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="org/app", display_name="app", source="fixture"
        ),
    )
    snapshot = await snapshots.create_snapshot(
        conn,
        repo,
        snapshots.SnapshotInput(
            commit_hash="commit", source_fingerprint="a" * 64, dirty=False
        ),
    )
    return repo, snapshot


def eid(repo: UUID, kind: str, key: str) -> str:
    return logical_id(str(repo), EntityType(kind), key)


async def entity(
    conn: asyncpg.Connection,
    repo: UUID,
    snap: UUID,
    kind: str,
    key: str,
    **fields: object,
) -> str:
    entity_id = eid(repo, kind, key)
    await insert(
        conn,
        "ucm_entities",
        snapshot_id=snap,
        repository_id=repo,
        entity_id=entity_id,
        entity_type=kind,
        logical_key=key,
        name=key,
        **fields,
    )
    return entity_id


async def graph(conn: asyncpg.Connection, repo: UUID, snap: UUID) -> dict[str, str]:
    ids = {}
    async with conn.transaction():
        for kind, key in [
            ("SOURCE_FILE", "A.java"),
            ("SYMBOL", "A.field"),
            ("SCOPE", "scope"),
            ("OCCURRENCE", "reference"),
            ("OPERATION", "call"),
            ("VALUE", "value"),
            ("RELATION", "consumes"),
            ("EXTERNAL_REFERENCE", "external"),
        ]:
            ids[key] = await entity(conn, repo, snap, kind, key)
        await insert(
            conn,
            "ucm_source_files",
            snapshot_id=snap,
            entity_id=ids["A.java"],
            path="A.java",
            language="java",
            content_sha256="a" * 64,
        )
        await insert(
            conn,
            "ucm_symbols",
            snapshot_id=snap,
            entity_id=ids["A.field"],
            symbol_kind="FIELD",
            qualified_name="A.field",
            scope_id=ids["scope"],
        )
        await insert(
            conn,
            "ucm_scopes",
            snapshot_id=snap,
            entity_id=ids["scope"],
            scope_kind="TYPE",
            owner_symbol_id=ids["A.field"],
        )
        await insert(
            conn,
            "ucm_occurrences",
            snapshot_id=snap,
            entity_id=ids["reference"],
            occurrence_kind="REFERENCE",
            scope_id=ids["scope"],
            resolution="RESOLVED",
            target_symbol_id=ids["A.field"],
        )
        await insert(
            conn,
            "ucm_values",
            snapshot_id=snap,
            entity_id=ids["value"],
            value_kind="LITERAL",
            partial=False,
            literal='"SQL text"',
        )
        await insert(
            conn,
            "ucm_operations",
            snapshot_id=snap,
            entity_id=ids["call"],
            operation_kind="CALL",
            scope_id=ids["scope"],
        )
        for position in (0, 1):
            await insert(
                conn,
                "ucm_operation_values",
                snapshot_id=snap,
                operation_id=ids["call"],
                direction="INPUT",
                position=position,
                value_id=ids["value"],
            )
        await insert(
            conn,
            "ucm_type_refs",
            snapshot_id=snap,
            owner_id=ids["value"],
            role="TYPE",
            position=0,
            name="String",
            resolution="UNRESOLVED",
        )
        common = {
            "certainty": "STATIC_PROVEN",
            "coverage_capability": "java.flow",
            "coverage_analyzer_version": "1",
            "coverage_status": "COMPLETE",
        }
        await insert(
            conn,
            "ucm_relations",
            snapshot_id=snap,
            entity_id=ids["consumes"],
            relation_kind="CONSUMES",
            source_id=ids["call"],
            source_type="OPERATION",
            target_id=ids["value"],
            target_type="VALUE",
            resolution="RESOLVED",
            **common,
        )
        await insert(
            conn,
            "ucm_external_references",
            snapshot_id=snap,
            entity_id=ids["external"],
            source_id=ids["call"],
            source_type="OPERATION",
            selector_kind="SYMBOL",
            qualified_name="lib.Client.send",
            parameter_type_names=[],
            reason="external",
            **common,
        )
        for owner, kind in [
            ("consumes", "RELATION"),
            ("external", "EXTERNAL_REFERENCE"),
        ]:
            await insert(
                conn,
                "ucm_evidence",
                snapshot_id=snap,
                owner_id=ids[owner],
                owner_type=kind,
                ordinal=0,
                source_file_id=ids["A.java"],
                start_line=1,
                start_byte_column=0,
                end_line=1,
                end_byte_column=1,
                analyzer="java",
                analyzer_version="1",
                rule="ast",
                description="static evidence",
            )
    return ids


def test_core_graph_and_registry(database_url: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snap = await setup(conn)
            ids = await graph(conn, repo, snap)
            assert await conn.fetchval("SELECT count(*) FROM ucm_entities") == len(ids)
            assert (
                await conn.fetchval("SELECT literal #>> '{}' FROM ucm_values")
                == "SQL text"
            )
            assert (
                await conn.fetchval(
                    "SELECT parameter_type_names FROM ucm_external_references"
                )
                == []
            )
            assert await conn.fetchval("SELECT count(*) FROM ucm_operation_values") == 2
            actual = {
                tuple(row)
                for row in await conn.fetch(
                    "SELECT relation_kind,source_type,target_type FROM ucm_relation_endpoints"
                )
            }
            assert actual == {
                (k.value, s.value, t.value)
                for k, pairs in relation_registry().items()
                for s, t in pairs
            }
            assert await conn.fetchval("SELECT count(*) FROM ucm_evidence") == 2
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_snapshot_and_repository_isolation(database_url: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, first = await setup(conn)
            ids = await graph(conn, repo, first)
            second = await snapshots.create_snapshot(
                conn,
                repo,
                snapshots.SnapshotInput(
                    commit_hash="second", source_fingerprint="b" * 64, dirty=False
                ),
            )
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                async with conn.transaction():
                    op = await entity(conn, repo, second, "OPERATION", "isolated")
                    await insert(
                        conn,
                        "ucm_operations",
                        snapshot_id=second,
                        entity_id=op,
                        operation_kind="CALL",
                        scope_id=ids["scope"],
                    )
            await graph(conn, repo, second)
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_entities WHERE entity_id=$1", ids["value"]
                )
                == 2
            )
            other = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="other", display_name="app", source="other"
                ),
            )
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await entity(conn, other, first, "VALUE", "foreign")
        finally:
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "problem",
    [
        "subtype",
        "endpoint",
        "candidate",
        "range",
        "payload",
        "path",
        "resolution",
        "selector",
    ],
)
def test_invalid_canonical_rows_rejected(database_url: str, problem: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snap = await setup(conn)
            ids = await graph(conn, repo, snap)
            with pytest.raises(
                (asyncpg.CheckViolationError, asyncpg.ForeignKeyViolationError)
            ):
                async with conn.transaction():
                    if problem == "subtype":
                        await insert(
                            conn,
                            "ucm_values",
                            snapshot_id=snap,
                            entity_id=ids["A.field"],
                            value_kind="UNKNOWN",
                            partial=True,
                        )
                    elif problem == "endpoint":
                        await conn.execute(
                            "UPDATE ucm_relations SET target_type='SYMBOL',target_id=$1 WHERE snapshot_id=$2",
                            ids["A.field"],
                            snap,
                        )
                    elif problem == "candidate":
                        await insert(
                            conn,
                            "ucm_relation_candidates",
                            snapshot_id=snap,
                            relation_id=ids["consumes"],
                            relation_kind="CONSUMES",
                            source_type="OPERATION",
                            candidate_id=ids["A.field"],
                            candidate_type="SYMBOL",
                        )
                    elif problem == "range":
                        await conn.execute(
                            "UPDATE ucm_evidence SET end_line=1,end_byte_column=0,start_byte_column=2"
                        )
                    elif problem == "payload":
                        await conn.execute("UPDATE ucm_values SET literal='{}'::jsonb")
                    elif problem == "path":
                        await conn.execute(
                            "UPDATE ucm_source_files SET path='../outside.java'"
                        )
                    elif problem == "resolution":
                        await conn.execute(
                            "UPDATE ucm_occurrences SET resolution='UNRESOLVED'"
                        )
                    else:
                        await conn.execute(
                            "UPDATE ucm_external_references SET http_method='GET'"
                        )
        finally:
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("state", ["VALIDATING", "READY", "PUBLISHED", "RETIRED"])
def test_frozen_snapshot_rejects_fact_writes(database_url: str, state: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snap = await setup(conn)
            await graph(conn, repo, snap)
            for current in ("VALIDATING", "READY", "PUBLISHED", "RETIRED"):
                await conn.execute(
                    "UPDATE ucm_snapshots SET state=$1 WHERE id=$2", current, snap
                )
                if current == state:
                    break
            for statement in (
                "UPDATE ucm_entities SET name='changed'",
                "DELETE FROM ucm_values",
                "UPDATE ucm_evidence SET description='changed'",
                "TRUNCATE ucm_operation_values",
            ):
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(statement)
            with pytest.raises(asyncpg.CheckViolationError):
                await entity(conn, repo, snap, "VALUE", "late")
            assert await conn.fetchval("SELECT count(*) FROM ucm_entities") == 8
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_state_transition_waits_for_fact_transaction(database_url: str) -> None:
    async def scenario() -> None:
        writer = await asyncpg.connect(database_url)
        transition = await asyncpg.connect(database_url)
        try:
            repo, snap = await setup(writer)
            tx = writer.transaction()
            await tx.start()
            try:
                await entity(writer, repo, snap, "VALUE", "in-flight")
                # A short server-side timeout proves the SHARE lock conflicts with state update.
                await transition.execute("SET lock_timeout='100ms'")
                with pytest.raises(asyncpg.LockNotAvailableError):
                    await transition.execute(
                        "UPDATE ucm_snapshots SET state='VALIDATING' WHERE id=$1", snap
                    )
                await tx.commit()
            except BaseException:
                if writer.is_in_transaction():
                    await tx.rollback()
                raise
            await transition.execute(
                "UPDATE ucm_snapshots SET state='VALIDATING' WHERE id=$1", snap
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await entity(writer, repo, snap, "VALUE", "too-late")
            assert await writer.fetchval("SELECT count(*) FROM ucm_entities") == 1
        finally:
            await writer.close()
            await transition.close()

    asyncio.run(scenario())


def test_fact_cannot_move_and_support_tables_cannot_be_truncated(
    database_url: str,
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo, snap = await setup(conn)
            await graph(conn, repo, snap)
            other = await snapshots.create_snapshot(
                conn,
                repo,
                snapshots.SnapshotInput(
                    commit_hash="other", source_fingerprint="b" * 64, dirty=True
                ),
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute("UPDATE ucm_entities SET snapshot_id=$1", other)
            tables = [
                "ucm_entities",
                "ucm_source_files",
                "ucm_symbols",
                "ucm_scopes",
                "ucm_occurrences",
                "ucm_operations",
                "ucm_values",
                "ucm_relations",
                "ucm_external_references",
                "ucm_evidence",
                "ucm_operation_values",
                "ucm_type_refs",
                "ucm_relation_candidates",
                "ucm_coverage_reasons",
            ]
            # CASCADE includes dependent tables, but BEFORE TRUNCATE must reject the operation.
            for table in tables:
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute(f"TRUNCATE public.{table} CASCADE")
            assert await conn.fetchval("SELECT count(*) FROM ucm_entities") == 8
        finally:
            await conn.close()

    asyncio.run(scenario())
