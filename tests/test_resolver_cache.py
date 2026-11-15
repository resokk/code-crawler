import asyncio
from uuid import UUID

import pytest
from test_resolver_context import selection

from code_crawler import cli, resolver_cache
from code_crawler.resolver_context import ResolverContext


def test_cache_key_binds_signature_source_context_generations_algorithm_and_limit():
    context = ResolverContext(
        mode="LATEST_INDEXED", selections=(selection(1), selection(2))
    )
    descriptor = {
        "snapshot_id": "source-version",
        "entity_id": "reference-id",
        "source_id": "origin",
        "selector_kind": "SYMBOL",
        "qualified_name": "api.Client.send",
        "parameter_type_names": [],
        "repository_hint": None,
        "version_hint": None,
    }
    key = resolver_cache.make_identity(descriptor, context, 50, "1")
    assert key == resolver_cache.make_identity(
        dict(reversed(list(descriptor.items()))), context, 50, "1"
    )
    changes = (
        resolver_cache.make_identity(
            {**descriptor, "parameter_type_names": None}, context, 50, "1"
        ),
        resolver_cache.make_identity(
            {**descriptor, "entity_id": "another-callsite"}, context, 50, "1"
        ),
        resolver_cache.make_identity(
            {**descriptor, "version_hint": "v2"}, context, 50, "1"
        ),
        resolver_cache.make_identity(descriptor, context, 1, "1"),
        resolver_cache.make_identity(descriptor, context, 50, "2"),
        resolver_cache.make_identity(
            descriptor,
            ResolverContext(mode="PINNED_SNAPSHOTS", selections=context.selections),
            50,
            "1",
        ),
        resolver_cache.make_identity(
            descriptor,
            context.model_copy(
                update={
                    "selections": (
                        context.selections[0],
                        context.selections[1].model_copy(
                            update={"generation": UUID(int=99)}
                        ),
                    )
                }
            ),
            50,
            "1",
        ),
    )
    assert len({key.cache_key, *[c.cache_key for c in changes]}) == 8


def test_cache_writer_checks_grants_and_ttl_before_database():
    context = ResolverContext(mode="LATEST_INDEXED", selections=(selection(1),))

    async def run():
        with pytest.raises(PermissionError):
            await resolver_cache.warm_resolver_cache(
                None, "repo1", "id", context, allowed_repositories=frozenset()
            )
        for ttl in (0, -1, 3601, True, "300"):
            with pytest.raises(ValueError, match="TTL"):
                await resolver_cache.warm_resolver_cache(
                    None,
                    "repo1",
                    "id",
                    context,
                    allowed_repositories=frozenset(("repo1",)),
                    ttl_seconds=ttl,
                )

    asyncio.run(run())


def test_cli_cache_commands_dispatch_without_changing_read_api(monkeypatch):
    import sys

    calls = []

    async def warm(**kwargs):
        calls.append(("warm", kwargs))

    async def prune():
        calls.append(("prune", {}))

    monkeypatch.setattr(cli, "resolver_cache_warm", warm)
    monkeypatch.setattr(cli, "resolver_cache_prune", prune)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "code-crawler",
            "resolver-cache",
            "warm",
            "context.json",
            "org/app",
            "reference-id",
            "--limit",
            "4",
            "--ttl-seconds",
            "60",
        ],
    )
    cli.main()
    monkeypatch.setattr(sys, "argv", ["code-crawler", "resolver-cache", "prune"])
    cli.main()
    assert calls == [
        (
            "warm",
            {
                "context_path": "context.json",
                "repository_key": "org/app",
                "reference_id": "reference-id",
                "limit": 4,
                "ttl_seconds": 60,
            },
        ),
        ("prune", {}),
    ]
