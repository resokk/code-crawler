import asyncio

import asyncpg
import pytest
from test_external_candidate_search import source_batch, target_batch
from test_publication import create, setup

from code_crawler import cross_repository, search, snapshots
from code_crawler.ingestion import UcmBatch
from code_crawler.publication import publish_snapshot, validate_snapshot
from code_crawler.resolver_context import select_context
from code_crawler.ucm import (
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    ExternalReference,
    Relation,
    RelationKind,
    Resolution,
    Symbol,
    SymbolSelector,
    logical_id,
)

pytestmark = pytest.mark.integration


def edge(repo, source, target, evidence, kind, key):
    return Relation(
        repository_id=str(repo),
        logical_key=key,
        id=logical_id(str(repo), EntityType.RELATION, key),
        name=key,
        relation_kind=kind,
        source=EntityRef(id=source.id, entity_type=source.entity_type),
        resolution=Resolution(
            status="RESOLVED",
            target=EntityRef(id=target.id, entity_type=target.entity_type),
        ),
        certainty=Certainty.STATIC_PROVEN,
        evidence=evidence,
        coverage=Coverage(
            capability="fixture.graph", analyzer_version="1", status="COMPLETE"
        ),
    )


async def fixture(conn, factory, count=0, cross_cycle=False):
    source = await setup(conn)
    target = await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="target", display_name="target", source="fixture"
        ),
    )
    batch, refs = source_batch(factory, source)
    method = next(e for e in batch.entities if isinstance(e, Symbol) and e.name == "m")
    ref = next(
        e
        for e in batch.entities
        if isinstance(e, ExternalReference) and e.id == refs["exact"]
    )
    relation = edge(
        source,
        method,
        ref,
        ref.evidence,
        RelationKind.EXTERNAL_DEPENDENCY,
        "graph.external",
    )
    batch = UcmBatch(repository_id=source, entities=(*batch.entities, relation))
    remote = target_batch(factory, target, count=count)
    remote_method = next(
        e for e in remote.entities if isinstance(e, Symbol) and e.name == "m"
    )
    cycle = edge(
        target,
        remote_method,
        remote_method,
        ref.evidence,
        RelationKind.CALLS,
        "graph.cycle",
    )
    # Evidence must belong to its own repository's archived source.
    proof = next(e for e in remote.entities if isinstance(e, Relation)).evidence
    cycle = cycle.model_copy(update={"evidence": proof})
    if cross_cycle:
        back_key = "graph.back"
        back = ref.model_copy(
            update={
                "repository_id": str(target),
                "logical_key": back_key,
                "id": logical_id(str(target), EntityType.EXTERNAL_REFERENCE, back_key),
                "source": EntityRef(
                    id=remote_method.id, entity_type=remote_method.entity_type
                ),
                "selector": SymbolSelector(
                    qualified_name=method.qualified_name,
                    parameter_type_names=("A", "String"),
                ),
                "evidence": proof,
            }
        )
        back_edge = edge(
            target,
            remote_method,
            back,
            proof,
            RelationKind.EXTERNAL_DEPENDENCY,
            "graph.back.edge",
        )
        remote = UcmBatch(
            repository_id=target, entities=(*remote.entities, back, back_edge)
        )
    else:
        remote = UcmBatch(repository_id=target, entities=(*remote.entities, cycle))
    src = await create(conn, source, batch)
    dst = await create(conn, target, remote)
    for repo, snap in ((source, src), (target, dst)):
        await validate_snapshot(conn, snap)
        await publish_snapshot(conn, repo, snap, expected_snapshot_id=None)
    grants = frozenset(("repo", "target"))
    context = await select_context(
        conn, "LATEST_INDEXED", ("repo", "target"), allowed_repositories=grants
    )
    return method, refs, context, grants


def test_two_repositories_cycle_and_bounds(database_url, ucm_batch_factory):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            method, refs, context, grants = await fixture(conn, ucm_batch_factory)

            async def trace(entity=method.id, **options):
                return await search.trace_cross_repository(
                    conn,
                    "repo",
                    entity,
                    context,
                    allowed_repositories=grants,
                    **options,
                )

            result = await trace()
            assert [s.kind for s in result.steps] == [
                "LOCAL_RELATION",
                "EXTERNAL_IDENTITY",
                "LOCAL_RELATION",
            ]
            assert [s.parent_step for s in result.steps] == [None, 0, 1]
            assert result.steps[-1].stop_reason == "CYCLE"
            assert result.steps[1].target.repository_key == "target"
            assert (
                result.steps[1].source.snapshot_id != result.steps[1].target.snapshot_id
            )
            assert result.steps[1].repository_hops == 1
            assert all(
                s.evidence and all(e.available for e in s.evidence)
                for s in result.steps
            )
            assert not result.truncated
            for options, reason in (
                ({"depth": 1}, "DEPTH_LIMIT"),
                ({"max_nodes": 1}, "NODE_LIMIT"),
                ({"max_results": 1}, "RESULT_LIMIT"),
                ({"max_repository_hops": 0}, "REPOSITORY_HOP_LIMIT"),
            ):
                bounded = await trace(**options)
                assert bounded.truncated and reason in bounded.reasons
                assert bounded.coverage.status == "PARTIAL"
            filtered = await trace(relation_kinds=(RelationKind.CALLS,))
            assert not filtered.steps
            partial = await trace(refs["partial"])
            assert partial.steps[0].resolution == "PARTIAL"
            assert not partial.steps[0].followed and partial.steps[0].target is None
            for name in ("missing", "kafka", "version"):
                unresolved = await trace(refs[name])
                assert not unresolved.steps[0].followed
            with pytest.raises(PermissionError):
                await search.trace_cross_repository(
                    None,
                    "repo",
                    method.id,
                    context,
                    allowed_repositories=frozenset(("repo",)),
                )
            for options in (
                {"depth": True},
                {"fanout": 0},
                {"max_nodes": 501},
                {"timeout_ms": 0},
                {"max_repository_hops": -1},
            ):
                with pytest.raises(ValueError):
                    await trace(**options)
            with pytest.raises(ValueError):
                await trace("ucm:" + "0" * 64)
            with pytest.raises(ValueError):
                async with conn.transaction():
                    await trace()
            assert await conn.fetchval("SELECT 1") == 1
        finally:
            await conn.close()

    asyncio.run(run())


def test_ambiguous_candidates_never_continue(database_url, ucm_batch_factory):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            method, refs, context, grants = await fixture(
                conn, ucm_batch_factory, count=3
            )
            result = await search.trace_cross_repository(
                conn, "repo", method.id, context, allowed_repositories=grants
            )
            step = result.steps[-1]
            assert step.resolution == "AMBIGUOUS"
            assert len(step.remote_candidates) == 4
            assert step.target is None and not step.followed
            assert len(result.steps) == 2
            bounded = await search.trace_cross_repository(
                conn,
                "repo",
                refs["exact"],
                context,
                allowed_repositories=grants,
                fanout=1,
                max_results=2,
            )
            assert bounded.truncated and bounded.result_units <= 2
            assert not bounded.steps[0].followed
        finally:
            await conn.close()

    asyncio.run(run())


def test_timeout_and_cancellation_recover_transaction(
    database_url, ucm_batch_factory, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            method, _, context, grants = await fixture(conn, ucm_batch_factory)
            entered = asyncio.Event()

            async def slow(self, conn, visit):
                entered.set()
                await conn.execute("SELECT pg_sleep(10)")

            monkeypatch.setattr(cross_repository._Walk, "local", slow)
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                result = await search.trace_cross_repository(
                    conn,
                    "repo",
                    method.id,
                    context,
                    allowed_repositories=grants,
                    timeout_ms=100,
                )
                assert result.truncated and "TIMEOUT" in result.reasons
                assert await conn.fetchval("SELECT 1") == 1
                entered.clear()
                task = asyncio.create_task(
                    search.trace_cross_repository(
                        conn, "repo", method.id, context, allowed_repositories=grants
                    )
                )
                await entered.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert await conn.fetchval("SELECT 1") == 1
        finally:
            await conn.close()

    asyncio.run(run())


def test_context_versions_rollback_and_foreign_snapshot(
    database_url, ucm_batch_factory
):
    from code_crawler.publication import rollback_publication

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            method, _, context, grants = await fixture(conn, ucm_batch_factory)

            async def trace(selected=context):
                return await search.trace_cross_repository(
                    conn, "repo", method.id, selected, allowed_repositories=grants
                )

            original = await trace()
            target = next(s for s in context.selections if s.repository_key == "target")
            source = next(s for s in context.selections if s.repository_key == "repo")
            forged = context.model_copy(
                update={
                    "selections": tuple(
                        s.model_copy(update={"snapshot_id": source.snapshot_id})
                        if s == target
                        else s
                        for s in context.selections
                    )
                }
            )
            with pytest.raises(ValueError):
                await trace(forged)
            changed = await create(
                conn,
                target.repository_id,
                target_batch(
                    ucm_batch_factory, target.repository_id, fqn="changed.Client.m"
                ),
            )
            await validate_snapshot(conn, changed)
            await publish_snapshot(
                conn,
                target.repository_id,
                changed,
                expected_snapshot_id=target.snapshot_id,
            )
            assert await trace() == original
            latest = await select_context(
                conn, "LATEST_INDEXED", ("repo", "target"), allowed_repositories=grants
            )
            assert (await trace(latest)).steps[-1].resolution == "UNRESOLVED"
            await rollback_publication(
                conn,
                target.repository_id,
                target.snapshot_id,
                expected_snapshot_id=changed,
            )
            restored = await select_context(
                conn, "LATEST_INDEXED", ("repo", "target"), allowed_repositories=grants
            )
            assert await trace(restored) == original
            # A deliberately narrower context discloses no private target candidate.
            narrow = await select_context(
                conn,
                "LATEST_INDEXED",
                ("repo",),
                allowed_repositories=frozenset(("repo",)),
            )
            hidden = await search.trace_cross_repository(
                conn,
                "repo",
                method.id,
                narrow,
                allowed_repositories=frozenset(("repo",)),
            )
            assert all(n.repository_key == "repo" for n in hidden.nodes)
            assert not hidden.steps[-1].remote_candidates
        finally:
            await conn.close()

    asyncio.run(run())


def test_cross_repository_cycle_depth_three(database_url, ucm_batch_factory):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            method, _, context, grants = await fixture(
                conn, ucm_batch_factory, cross_cycle=True
            )
            bounded = await search.trace_cross_repository(
                conn, "repo", method.id, context, allowed_repositories=grants, depth=3
            )
            assert max(s.depth for s in bounded.steps) == 3
            assert bounded.truncated and "DEPTH_LIMIT" in bounded.reasons
            complete = await search.trace_cross_repository(
                conn, "repo", method.id, context, allowed_repositories=grants, depth=6
            )
            assert complete.steps[-1].target == complete.root
            assert complete.steps[-1].stop_reason == "CYCLE"
            assert complete.steps[-1].repository_hops == 2
            assert not complete.truncated
        finally:
            await conn.close()

    asyncio.run(run())
