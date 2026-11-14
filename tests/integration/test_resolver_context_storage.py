import asyncio

import asyncpg
import pytest
from test_publication import create, setup

from code_crawler import snapshots
from code_crawler.jobs import collect_garbage
from code_crawler.publication import (
    publish_snapshot,
    rollback_publication,
    validate_snapshot,
)
from code_crawler.resolver_context import (
    DeploymentBinding,
    SnapshotPin,
    load_context,
    register_deployment,
    release_context,
    release_deployment,
    save_context,
    select_context,
    verify_context,
)

pytestmark = pytest.mark.integration


def test_context_versions_deployments_authorization_and_retention(
    database_url, ucm_batch_factory
):
    async def run():
        conn = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            second = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="two", display_name="two", source="fixture"
                ),
            )
            one = await create(conn, repo, ucm_batch_factory(repo))
            two = await create(conn, second, ucm_batch_factory(second))
            for r, s in ((repo, one), (second, two)):
                await validate_snapshot(conn, s)
                await publish_snapshot(conn, r, s, expected_snapshot_id=None)
            grants = frozenset(("repo", "two"))
            keys = ("repo", "two")
            latest = await select_context(
                conn, "LATEST_INDEXED", keys, allowed_repositories=grants
            )
            pins = (
                SnapshotPin(repository_key="repo", snapshot_id=one),
                SnapshotPin(repository_key="two", snapshot_id=two),
            )
            pinned = await select_context(
                conn, "PINNED_SNAPSHOTS", keys, pins=pins, allowed_repositories=grants
            )
            context_id = await save_context(conn, pinned, allowed_repositories=grants)
            assert (
                await save_context(conn, pinned, allowed_repositories=grants)
                == context_id
            )
            assert (
                await load_context(conn, context_id, allowed_repositories=grants)
                == pinned
            )
            with pytest.raises(PermissionError):
                await load_context(
                    conn, context_id, allowed_repositories=frozenset(("repo",))
                )
            with pytest.raises(ValueError, match="another repository"):
                await select_context(
                    conn,
                    "PINNED_SNAPSHOTS",
                    keys,
                    pins=(
                        SnapshotPin(repository_key="repo", snapshot_id=two),
                        SnapshotPin(repository_key="two", snapshot_id=one),
                    ),
                    allowed_repositories=grants,
                )
            with pytest.raises(ValueError, match="deployment mapping"):
                await select_context(
                    conn,
                    "DEPLOYMENT_CONTEXT",
                    keys,
                    deployment_key="unknown",
                    allowed_repositories=grants,
                )
            bindings = (
                DeploymentBinding(
                    repository_key="repo", snapshot_id=one, service_key="app"
                ),
                DeploymentBinding(
                    repository_key="two", snapshot_id=two, service_key="worker"
                ),
            )
            await register_deployment(
                conn, "deploy-1", bindings, allowed_repositories=grants
            )
            deployed = await select_context(
                conn,
                "DEPLOYMENT_CONTEXT",
                keys,
                deployment_key="deploy-1",
                allowed_repositories=grants,
            )
            assert deployed.selections[0].services == ("app",)
            new = await create(conn, second, ucm_batch_factory(second))
            await validate_snapshot(conn, new)
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                before = await select_context(
                    conn, "LATEST_INDEXED", keys, allowed_repositories=grants
                )
                await publish_snapshot(other, second, new, expected_snapshot_id=two)
                stable = await select_context(
                    conn, "LATEST_INDEXED", keys, allowed_repositories=grants
                )
                assert stable == before
            updated = await select_context(
                conn, "LATEST_INDEXED", keys, allowed_repositories=grants
            )
            assert updated.fingerprint != latest.fingerprint
            assert (
                await load_context(conn, context_id, allowed_repositories=grants)
                == pinned
            )
            assert not await verify_context(conn, pinned, allowed_repositories=grants)
            assert not (await collect_garbage(conn, keep_retired=0))["retired"]
            await release_context(conn, context_id, allowed_repositories=grants)
            assert not (await collect_garbage(conn, keep_retired=0))["retired"]
            await release_deployment(conn, "deploy-1", allowed_repositories=grants)
            assert two in (await collect_garbage(conn, keep_retired=0))["retired"]
            with pytest.raises(ValueError, match="snapshot missing"):
                await verify_context(conn, pinned, allowed_repositories=grants)
            # A failed context request never changes a publication or creates pins.
            building = await create(conn, repo, ucm_batch_factory(repo))
            with pytest.raises(ValueError):
                await select_context(
                    conn,
                    "PINNED_SNAPSHOTS",
                    ("repo",),
                    pins=(SnapshotPin(repository_key="repo", snapshot_id=building),),
                    allowed_repositories=grants,
                )
            assert (await snapshots.published_snapshot(conn, repo))["id"] == one
            await rollback_publication(conn, repo, one, expected_snapshot_id=one)
        finally:
            await other.close()
            await conn.close()

    asyncio.run(run())
