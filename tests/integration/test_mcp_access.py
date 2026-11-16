import asyncio
import json

import asyncpg
import pytest
from fastmcp.server.auth import AccessToken
from test_access import TOOLS, call_http, http_client
from test_publication import create, setup

from code_crawler import access, search, snapshots
from code_crawler.access import authorized_evidence
from code_crawler.publication import publish_snapshot, validate_snapshot
from code_crawler.resolver_context import select_context
from code_crawler.ucm import Relation, Symbol

pytestmark = pytest.mark.integration


def test_two_principals_all_tools_http_isolation_and_evidence(
    database_url, access_policy_config, ucm_batch_factory, monkeypatch, caplog
):
    tokens, _ = access_policy_config
    monkeypatch.setenv("DATABASE_URL", database_url)
    caplog.set_level("INFO", logger="code_crawler.audit")

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await setup(conn)
            fixtures = {}
            for key in ("app", "other"):
                repo = await snapshots.register_repository(
                    conn,
                    snapshots.RepositoryInput(
                        repository_key=key, display_name=key, source="fixture"
                    ),
                )
                batch = ucm_batch_factory(repo)
                snapshot = await create(conn, repo, batch)
                await validate_snapshot(conn, snapshot)
                await publish_snapshot(conn, repo, snapshot, expected_snapshot_id=None)
                fixtures[key] = (repo, snapshot, batch)
            before = await conn.fetchval("SELECT count(*) FROM ucm_entities")
            contexts = {}
            for own, foreign in (("app", "other"), ("other", "app")):
                contexts[own] = (
                    await select_context(
                        conn,
                        "LATEST_INDEXED",
                        (own,),
                        allowed_repositories=frozenset({own}),
                    ),
                    await select_context(
                        conn,
                        "LATEST_INDEXED",
                        (own, foreign),
                        allowed_repositories=frozenset({own, foreign}),
                    ),
                )
            async with http_client() as client:

                async def check(principal, own, foreign):
                    batch = fixtures[own][2]
                    symbol = next(e for e in batch.entities if isinstance(e, Symbol))
                    relation = next(
                        e for e in batch.entities if isinstance(e, Relation)
                    )
                    for tool, defaults in TOOLS.items():
                        args = {**defaults, "repository_key": own}
                        if "symbol_id" in args:
                            args["symbol_id"] = symbol.id
                        if "entity_id" in args:
                            args["entity_id"] = symbol.id
                        if "relation_id" in args:
                            args["relation_id"] = relation.id
                        response = await call_http(
                            client, tokens[principal], tool, args
                        )
                        assert response.status_code == 200, response.text
                        result = response.json()["result"]
                        assert not result.get("isError"), (tool, result)
                        assert str(fixtures[foreign][1]) not in response.text
                        for denied_repo in (foreign, "does-not-exist"):
                            denied = await call_http(
                                client,
                                tokens[principal],
                                tool,
                                {**args, "repository_key": denied_repo},
                            )
                            assert denied.json()["result"]["isError"]
                            assert "access denied" in denied.text
                            assert denied_repo not in denied.text
                    selected, mixed = contexts[own]
                    cross_args = {
                        "repository_key": own,
                        "entity_id": symbol.id,
                        "context": selected.model_dump(mode="json"),
                    }
                    cross = await call_http(
                        client, tokens[principal], "trace_cross_repository", cross_args
                    )
                    assert not cross.json()["result"].get("isError"), cross.text
                    for denied_args in (
                        {**cross_args, "context": mixed.model_dump(mode="json")},
                        {**cross_args, "repository_key": foreign},
                    ):
                        denied = await call_http(
                            client,
                            tokens[principal],
                            "trace_cross_repository",
                            denied_args,
                        )
                        assert "access denied" in denied.text
                        assert foreign not in denied.text
                    forged = selected.model_dump(mode="json")
                    forged["selections"][0]["repository_id"] = str(fixtures[foreign][0])
                    forged["selections"][0]["snapshot_id"] = str(fixtures[foreign][1])
                    denied = await call_http(
                        client,
                        tokens[principal],
                        "trace_cross_repository",
                        {**cross_args, "context": forged},
                    )
                    assert "query failed" in denied.text
                    assert foreign not in denied.text
                    result = await call_http(
                        client,
                        tokens[principal],
                        "search_discovery_entries",
                        {"kind": "SYMBOL", "lookup_key": "A"},
                    )
                    assert not result.json()["result"].get("isError"), result.text
                    assert foreign not in result.text
                    denied = await call_http(
                        client,
                        tokens[principal],
                        "search_discovery_entries",
                        {
                            "kind": "SYMBOL",
                            "lookup_key": "A",
                            "repository_keys": [foreign],
                        },
                    )
                    assert "access denied" in denied.text

                await asyncio.gather(
                    check("alice", "app", "other"), check("bob", "other", "app")
                )

                # A DB exception with source bytes must not escape the tool boundary.
                async def broken(*args, **kwargs):
                    raise asyncpg.DataError("secret/path.java SELECT super_secret")

                monkeypatch.setattr(search, "search_symbols", broken)
                failure = await call_http(
                    client,
                    tokens["alice"],
                    "search_symbols",
                    {"repository_key": "app", "name": "A"},
                )
                assert "query failed" in failure.text
                assert (
                    "super_secret" not in failure.text
                    and "path.java" not in failure.text
                )
            credential = AccessToken(
                token=tokens["alice"], client_id="bob", scopes=["source"]
            )
            relation = next(
                e for e in fixtures["app"][2].entities if isinstance(e, Relation)
            )
            fragments = await authorized_evidence(
                conn, access.load_policy(), credential, "app", relation.id
            )
            assert fragments and all(f.source is not None for f in fragments)
            with pytest.raises(PermissionError, match="access denied"):
                await authorized_evidence(
                    conn, access.load_policy(), credential, "other", relation.id
                )
            with pytest.raises(ValueError):
                foreign_relation = next(
                    e for e in fixtures["other"][2].entities if isinstance(e, Relation)
                )
                await authorized_evidence(
                    conn, access.load_policy(), credential, "app", foreign_relation.id
                )
            assert before == await conn.fetchval("SELECT count(*) FROM ucm_entities")
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_snapshots WHERE state='PUBLISHED'"
                )
                == 2
            )
        finally:
            await conn.close()

    asyncio.run(run())
    events = [
        json.loads(r.message) for r in caplog.records if r.name == "code_crawler.audit"
    ]
    assert {e["principal"] for e in events if e["allowed"]} >= {"alice", "bob"}
    assert any(not e["allowed"] for e in events)
    assert all(token not in caplog.text for token in tokens.values())
