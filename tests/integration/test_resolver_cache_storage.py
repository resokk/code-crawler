import asyncio
import hashlib
import json
import logging
from contextlib import asynccontextmanager

import asyncpg
import pytest
from test_external_candidate_search import source_batch, target_batch
from test_publication import create, setup

from code_crawler import (
    discovery,
    external_candidates,
    resolver_cache,
    search,
    snapshots,
)
from code_crawler.jobs import collect_garbage
from code_crawler.publication import (
    publish_snapshot,
    rollback_publication,
    validate_snapshot,
)
from code_crawler.resolver_context import (
    DeploymentBinding,
    SnapshotPin,
    register_deployment,
    release_deployment,
    select_context,
)

pytestmark = pytest.mark.integration


async def fixture(conn, factory):
    source = await setup(conn)
    target = await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="target", display_name="target", source="fixture"
        ),
    )
    batch, refs = source_batch(factory, source)
    src = await create(conn, source, batch)
    dst = await create(conn, target, target_batch(factory, target))
    for repo, snap in ((source, src), (target, dst)):
        await validate_snapshot(conn, snap)
        await publish_snapshot(conn, repo, snap, expected_snapshot_id=None)
    grants = frozenset(("repo", "target"))
    context = await select_context(
        conn, "LATEST_INDEXED", ("repo", "target"), allowed_repositories=grants
    )
    return source, target, src, dst, refs, context, grants


def test_cache_hit_miss_expiry_corruption_bounds_and_read_only(
    database_url, ucm_batch_factory, caplog, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            _, _, _, _, refs, context, grants = await fixture(conn, ucm_batch_factory)

            async def resolve(ref="exact", limit=50):
                return await search.resolve_external_reference(
                    conn,
                    "repo",
                    refs[ref],
                    context,
                    allowed_repositories=grants,
                    limit=limit,
                )

            uncached = await resolve()
            assert uncached.status == "RESOLVED"
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_entries") == 0
            )
            warmed = await resolver_cache.warm_resolver_cache(
                conn, "repo", refs["exact"], context, allowed_repositories=grants
            )
            assert warmed.stored and warmed.result == uncached
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_dependencies")
                == 2
            )
            caplog.clear()
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                assert await resolve() == uncached
            assert any(
                getattr(r, "cache_status", None) == "HIT" for r in caplog.records
            )
            # Hits bypass canonical target/Evidence hydration, not authorization/context checks.
            original_reader = external_candidates.selected_reader

            def no_hydration(*args, **kwargs):
                raise AssertionError("cache hit must not hydrate C04 again")

            with monkeypatch.context() as patch:
                patch.setattr(external_candidates, "selected_reader", no_hydration)
                assert await resolve() == uncached
                with pytest.raises(PermissionError):
                    await search.resolve_external_reference(
                        conn,
                        "repo",
                        refs["exact"],
                        context,
                        allowed_repositories=frozenset(("repo",)),
                    )
            await conn.execute(
                "UPDATE resolver_cache_entries SET created_at=clock_timestamp()-interval '10 minutes',expires_at=clock_timestamp()-interval '1 minute'"
            )
            caplog.clear()
            assert await resolve() == uncached
            assert any(
                getattr(r, "cache_reason", None) == "EXPIRED" for r in caplog.records
            )
            warmed = await resolver_cache.warm_resolver_cache(
                conn, "repo", refs["exact"], context, allowed_repositories=grants
            )
            await conn.execute(
                "UPDATE resolver_cache_entries SET payload='{}' WHERE cache_key=$1",
                warmed.cache_key,
            )
            caplog.clear()
            assert await resolve() == uncached
            assert any(
                getattr(r, "cache_reason", None) == "INVALID_ENTRY"
                for r in caplog.records
            )
            await resolver_cache.warm_resolver_cache(
                conn, "repo", refs["exact"], context, allowed_repositories=grants
            )
            payload = json.loads(warmed.result.model_dump_json())
            payload["context_fingerprint"] = "0" * 64
            text = json.dumps(payload)
            await conn.execute(
                "UPDATE resolver_cache_entries SET payload=$2,payload_sha256=$3 WHERE cache_key=$1",
                warmed.cache_key,
                text,
                hashlib.sha256(text.encode()).hexdigest(),
            )
            caplog.clear()
            assert await resolve() == uncached
            assert any(
                getattr(r, "cache_reason", None) == "INVALID_SCOPE"
                for r in caplog.records
            )
            await conn.execute("DELETE FROM resolver_cache_entries")
            assert await resolve() == uncached
            for name, status in (
                ("partial", "PARTIAL"),
                ("missing", "UNRESOLVED"),
                ("name", "PARTIAL"),
            ):
                result = await resolver_cache.warm_resolver_cache(
                    conn, "repo", refs[name], context, allowed_repositories=grants
                )
                assert result.stored and result.result.status == status
                assert await resolve(name) == result.result
            for name in ("partial", "name"):
                weak = await resolver_cache.warm_resolver_cache(
                    conn, "repo", refs[name], context, allowed_repositories=grants
                )
                forged = json.loads(weak.result.model_dump_json())
                candidate = forged["candidates"][0]
                candidate["certainty"] = "STATIC_PROVEN"
                candidate["coverage"].update(status="COMPLETE", reasons=[])
                forged.update(status="RESOLVED", target=candidate, reasons=[])
                forged["coverage"].update(status="COMPLETE", reasons=[])
                text = json.dumps(forged)
                external_candidates.CandidateResolution.model_validate_json(text)
                await conn.execute(
                    "UPDATE resolver_cache_entries SET payload=$2,payload_sha256=$3 WHERE cache_key=$1",
                    weak.cache_key,
                    text,
                    hashlib.sha256(text.encode()).hexdigest(),
                )
                caplog.clear()
                assert (await resolve(name)).status == "PARTIAL"
                assert any(
                    getattr(r, "cache_reason", None) == "INVALID_SCOPE"
                    for r in caplog.records
                )
            monkeypatch.setattr(resolver_cache, "MAX_ENTRIES", 2)
            pruned = await resolver_cache.prune_resolver_cache(conn)
            assert (
                pruned == 1
                and await conn.fetchval("SELECT count(*) FROM resolver_cache_entries")
                == 2
            )
            warmed = await resolver_cache.warm_resolver_cache(
                conn,
                "repo",
                refs["exact"],
                context,
                allowed_repositories=grants,
                limit=1,
            )
            assert warmed.stored and warmed.evicted_entries == 1
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_entries") == 2
            )
            caplog.clear()
            await resolve(limit=2)
            assert any(
                getattr(r, "cache_status", None) == "MISS" for r in caplog.records
            )
            assert original_reader is external_candidates.selected_reader
        finally:
            await conn.close()

    caplog.set_level(logging.INFO, logger="code_crawler.resolver_cache")
    asyncio.run(run())


def test_cache_context_versions_rollback_gc_and_algorithm_invalidation(
    database_url, ucm_batch_factory, caplog, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        try:
            _, target, _src, dst, refs, context, grants = await fixture(
                conn, ucm_batch_factory
            )

            async def warm(ctx):
                return await resolver_cache.warm_resolver_cache(
                    conn, "repo", refs["exact"], ctx, allowed_repositories=grants
                )

            original = await warm(context)
            pins = tuple(
                SnapshotPin(repository_key=s.repository_key, snapshot_id=s.snapshot_id)
                for s in context.selections
            )
            pinned = await select_context(
                conn,
                "PINNED_SNAPSHOTS",
                ("repo", "target"),
                pins=pins,
                allowed_repositories=grants,
            )
            pinned_cache = await warm(pinned)
            await register_deployment(
                conn,
                "deploy",
                tuple(
                    DeploymentBinding(
                        repository_key=s.repository_key,
                        snapshot_id=s.snapshot_id,
                        service_key=s.repository_key,
                    )
                    for s in context.selections
                ),
                allowed_repositories=grants,
            )
            deployed = await select_context(
                conn,
                "DEPLOYMENT_CONTEXT",
                ("repo", "target"),
                deployment_key="deploy",
                allowed_repositories=grants,
            )
            deployed_cache = await warm(deployed)
            assert (
                len(
                    {
                        original.cache_key,
                        pinned_cache.cache_key,
                        deployed_cache.cache_key,
                    }
                )
                == 3
            )
            changed = await create(
                conn,
                target,
                target_batch(ucm_batch_factory, target, fqn="changed.Client.m"),
            )
            await validate_snapshot(conn, changed)
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                before = await search.resolve_external_reference(
                    conn, "repo", refs["exact"], context, allowed_repositories=grants
                )
                await publish_snapshot(other, target, changed, expected_snapshot_id=dst)
                again = await search.resolve_external_reference(
                    conn, "repo", refs["exact"], context, allowed_repositories=grants
                )
                assert before == again == original.result
            latest = await select_context(
                conn, "LATEST_INDEXED", ("repo", "target"), allowed_repositories=grants
            )
            caplog.clear()
            fresh = await search.resolve_external_reference(
                conn, "repo", refs["exact"], latest, allowed_repositories=grants
            )
            assert fresh.status == "UNRESOLVED"
            assert not any(
                getattr(r, "cache_status", None) == "HIT" for r in caplog.records
            )
            await rollback_publication(conn, target, dst, expected_snapshot_id=changed)
            restored = await select_context(
                conn, "LATEST_INDEXED", ("repo", "target"), allowed_repositories=grants
            )
            assert restored.fingerprint == context.fingerprint
            caplog.clear()
            assert (
                await search.resolve_external_reference(
                    conn, "repo", refs["exact"], restored, allowed_repositories=grants
                )
                == original.result
            )
            assert any(
                getattr(r, "cache_status", None) == "HIT" for r in caplog.records
            )
            with monkeypatch.context() as patch:
                patch.setattr(external_candidates, "VERSION", "changed")
                caplog.clear()
                changed_algorithm = await search.resolve_external_reference(
                    conn, "repo", refs["exact"], restored, allowed_repositories=grants
                )
                assert changed_algorithm.status == original.result.status
                assert changed_algorithm.target.target == original.result.target.target
                assert changed_algorithm.coverage.analyzer_version == "changed"
                assert not any(
                    getattr(r, "cache_status", None) == "HIT" for r in caplog.records
                )
            await rollback_publication(conn, target, changed, expected_snapshot_id=dst)
            # Deployment pins are explicit; cache dependencies themselves must never pin snapshots.
            from code_crawler.resolver_context import release_deployment

            await release_deployment(conn, "deploy", allowed_repositories=grants)
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                retained = await search.resolve_external_reference(
                    conn, "repo", refs["exact"], context, allowed_repositories=grants
                )
                assert retained == original.result
                guarded = await collect_garbage(other, keep_retired=0)
                assert dst not in guarded["retired"] and dst in guarded["skipped"]
            assert dst in (await collect_garbage(conn, keep_retired=0))["retired"]
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_entries") == 0
            )
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_dependencies")
                == 0
            )
        finally:
            await other.close()
            await conn.close()

    caplog.set_level(logging.INFO, logger="code_crawler.resolver_cache")
    asyncio.run(run())


def test_generation_race_skips_cache_write_and_cascades_existing_entries(
    database_url, ucm_batch_factory, caplog, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        try:
            _, _, _, _, refs, context, grants = await fixture(conn, ucm_batch_factory)
            original = await resolver_cache.warm_resolver_cache(
                conn, "repo", refs["exact"], context, allowed_repositories=grants
            )
            assert original.stored
            identity = resolver_cache._identity
            switched = False

            async def change_after_read(*args, **kwargs):
                nonlocal switched
                key = await identity(*args, **kwargs)
                if not switched:
                    switched = True
                    with monkeypatch.context() as patch:
                        patch.setattr(discovery, "VERSION", "discovery/future")
                        await discovery.refresh_discovery(other, "target")
                return key

            with monkeypatch.context() as patch:
                patch.setattr(resolver_cache, "_identity", change_after_read)
                raced = await resolver_cache.warm_resolver_cache(
                    conn, "repo", refs["exact"], context, allowed_repositories=grants
                )
            assert raced.result == original.result
            assert not raced.stored and raced.reason == "CONTEXT_CHANGED"
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_entries") == 0
            )
            caplog.clear()
            result = await search.resolve_external_reference(
                conn, "repo", refs["exact"], context, allowed_repositories=grants
            )
            assert (
                result.status == "PARTIAL"
                and "target" in result.unavailable_repositories
            )
            assert any(
                getattr(r, "cache_status", None) == "BYPASS" for r in caplog.records
            )
        finally:
            await other.close()
            await conn.close()

    caplog.set_level(logging.INFO, logger="code_crawler.resolver_cache")
    asyncio.run(run())


def test_concurrent_warmers_obey_capacity_and_oversized_results_are_not_stored(
    database_url, ucm_batch_factory, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        workers = []
        try:
            _, _, _, _, refs, context, grants = await fixture(conn, ucm_batch_factory)
            workers = [await asyncpg.connect(database_url) for _ in range(3)]
            with monkeypatch.context() as patch:
                patch.setattr(resolver_cache, "MAX_PAYLOAD_BYTES", 1)
                oversized = await resolver_cache.warm_resolver_cache(
                    conn, "repo", refs["exact"], context, allowed_repositories=grants
                )
            assert not oversized.stored and oversized.reason == "OVERSIZED"
            assert oversized.result.status == "RESOLVED"
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_entries") == 0
            )
            monkeypatch.setattr(resolver_cache, "MAX_ENTRIES", 2)
            warmed = await asyncio.gather(
                *(
                    resolver_cache.warm_resolver_cache(
                        worker, "repo", refs[name], context, allowed_repositories=grants
                    )
                    for worker, name in zip(workers, ("exact", "missing", "partial"))
                )
            )
            assert all(r.stored for r in warmed)
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_entries") == 2
            )
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_dependencies")
                == 4
            )
        finally:
            for worker in workers:
                await worker.close()
            await conn.close()

    asyncio.run(run())


def test_missing_cache_schema_is_not_a_resolver_dependency(
    database_url, ucm_batch_factory, caplog, monkeypatch
):
    from code_crawler import db

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            names = db.migration_names()
            with monkeypatch.context() as patch:
                patch.setattr(
                    db, "migration_names", lambda: [n for n in names if n < "0028"]
                )
                _, _, _, _, refs, context, grants = await fixture(
                    conn, ucm_batch_factory
                )
            assert (
                await conn.fetchval(
                    "SELECT to_regclass('public.resolver_cache_entries')"
                )
                is None
            )
            result = await search.resolve_external_reference(
                conn, "repo", refs["exact"], context, allowed_repositories=grants
            )
            assert result.status == "RESOLVED"
            assert any(
                getattr(r, "cache_reason", None) == "STORAGE_UNAVAILABLE"
                for r in caplog.records
            )
        finally:
            await conn.close()

    caplog.set_level(logging.INFO, logger="code_crawler.resolver_cache")
    asyncio.run(run())


def test_cli_warm_prune_and_cache_hit_query_reduction(
    database_url, ucm_batch_factory, monkeypatch, tmp_path, request
):
    from io import StringIO

    from rich.console import Console

    from code_crawler import cli

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            _, _, _, _, refs, context, grants = await fixture(conn, ucm_batch_factory)
            queries = []
            with conn.query_logger(lambda logged: queries.append(logged.query)):
                uncached = await search.resolve_external_reference(
                    conn, "repo", refs["exact"], context, allowed_repositories=grants
                )
                await asyncio.sleep(0)
            cold_count = len(queries)
            manifest = tmp_path / "context.json"
            manifest.write_text(context.model_dump_json())
            output = StringIO()
            monkeypatch.setenv("DATABASE_URL", database_url)
            monkeypatch.setattr(cli, "console", Console(file=output, width=120))
            await cli.resolver_cache_warm(
                str(manifest), "repo", refs["exact"], ttl_seconds=3600
            )
            report = json.loads(output.getvalue())
            assert report["stored"] and report["resolution"] == "RESOLVED"
            lifetime = await conn.fetchval(
                "SELECT extract(epoch FROM expires_at-created_at) FROM resolver_cache_entries"
            )
            assert lifetime == 3600
            queries.clear()
            with conn.query_logger(lambda logged: queries.append(logged.query)):
                cached = await search.resolve_external_reference(
                    conn, "repo", refs["exact"], context, allowed_repositories=grants
                )
                await asyncio.sleep(0)
            assert cached == uncached and len(queries) < cold_count
            request.node.user_properties.extend(
                (
                    ("cache_miss_queries", cold_count),
                    ("cache_hit_queries", len(queries)),
                )
            )
            await conn.execute(
                "UPDATE resolver_cache_entries SET created_at=clock_timestamp()-interval '10 minutes',expires_at=clock_timestamp()-interval '1 minute'"
            )
            output.seek(0)
            output.truncate()
            await cli.resolver_cache_prune()
            assert json.loads(output.getvalue())["removed_entries"] == 1
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_entries") == 0
            )
        finally:
            await conn.close()

    asyncio.run(run())


@pytest.mark.parametrize("change", ["snapshot_gc", "deployment_release"])
def test_context_removed_after_compute_skips_cache_write(
    database_url, ucm_batch_factory, change
):
    async def run():
        conn = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        try:
            _, target, src, dst, refs, context, grants = await fixture(
                conn, ucm_batch_factory
            )
            replacement = await create(
                other, target, target_batch(ucm_batch_factory, target)
            )
            await validate_snapshot(other, replacement)
            if change == "deployment_release":
                await register_deployment(
                    conn,
                    "cache-window",
                    (
                        DeploymentBinding(
                            repository_key="repo", snapshot_id=src, service_key="app"
                        ),
                        DeploymentBinding(
                            repository_key="target",
                            snapshot_id=dst,
                            service_key="library",
                        ),
                    ),
                    allowed_repositories=grants,
                )
                context = await select_context(
                    conn,
                    "DEPLOYMENT_CONTEXT",
                    ("repo", "target"),
                    allowed_repositories=grants,
                    deployment_key="cache-window",
                )
            baseline = await search.resolve_external_reference(
                conn, "repo", refs["exact"], context, allowed_repositories=grants
            )
            source_rows = await conn.fetchval(
                "SELECT count(*) FROM ucm_entities WHERE snapshot_id=$1", src
            )

            class RaceConnection:
                switched = False

                def __getattr__(self, name):
                    return getattr(conn, name)

                @asynccontextmanager
                async def transaction(self, **kwargs):
                    if not kwargs.get("readonly") and not self.switched:
                        self.switched = True
                        if change == "snapshot_gc":
                            await publish_snapshot(
                                other, target, replacement, expected_snapshot_id=dst
                            )
                            collected = await collect_garbage(other, keep_retired=0)
                            assert dst in collected["retired"]
                        else:
                            await release_deployment(
                                other, "cache-window", allowed_repositories=grants
                            )
                    async with conn.transaction(**kwargs):
                        yield

            report = await resolver_cache.warm_resolver_cache(
                RaceConnection(),
                "repo",
                refs["exact"],
                context,
                allowed_repositories=grants,
            )
            assert not report.stored and report.reason == "CONTEXT_CHANGED"
            assert report.result == baseline
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_entries") == 0
            )
            assert (
                await conn.fetchval("SELECT count(*) FROM resolver_cache_dependencies")
                == 0
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_entities WHERE snapshot_id=$1", src
                )
                == source_rows
            )
        finally:
            await conn.close()
            await other.close()

    asyncio.run(run())
