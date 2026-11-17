import asyncio
import copy
import json
from contextlib import asynccontextmanager

import httpx2 as httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken

from code_crawler import server
from code_crawler.access import authorized_evidence, load_policy

ID = "ucm:" + "a" * 64
TOOLS = {
    "search_symbols": {"name": "A"},
    "search_text": {"query": "A"},
    "find_callers": {"symbol_id": ID},
    "find_callees": {"symbol_id": ID},
    "find_sql_executions": {},
    "find_table_readers": {"table": "users"},
    "find_table_writers": {"table": "users"},
    "trace_dependency": {"entity_id": ID},
    "get_evidence": {"relation_id": ID},
    "get_monitoring": {},
}


@asynccontextmanager
async def http_client():
    app = server.mcp.http_app(
        stateless_http=True,
        json_response=True,
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client,
    ):
        yield client


async def call_http(client, token, tool, args):
    return await client.post(
        "/mcp",
        headers={
            "authorization": "Bearer " + token,
            "accept": "application/json, text/event-stream",
            "mcp-protocol-version": "2025-06-18",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        },
    )


@pytest.mark.parametrize(
    "mutation",
    ["empty", "duplicate", "duplicate_token", "unknown", "wildcard", "expired"],
)
def test_policy_invalid_or_expired(access_policy_config, monkeypatch, mutation):
    tokens, original = access_policy_config
    policy = copy.deepcopy(original)
    if mutation == "empty":
        monkeypatch.delenv("MCP_ACCESS_POLICY")
    elif mutation == "duplicate":
        policy["principals"].append(policy["principals"][0])
    elif mutation == "duplicate_token":
        policy["principals"][1]["token_sha256"] = policy["principals"][0][
            "token_sha256"
        ]
    elif mutation == "unknown":
        policy["principals"][0]["permissions"] = ["admin"]
    elif mutation == "wildcard":
        policy["principals"][0]["repositories"] = ["*"]
    else:
        policy["principals"][0]["expires_at"] = 1
    if mutation != "empty":
        monkeypatch.setenv("MCP_ACCESS_POLICY", json.dumps(policy))
    if mutation == "expired":
        with pytest.raises(PermissionError, match="access denied"):
            load_policy().authenticate(tokens["alice"])
    else:
        with pytest.raises(
            RuntimeError, match="valid MCP_ACCESS_POLICY is required"
        ) as error:
            load_policy()
        assert tokens["alice"] not in str(error.value)


def test_http_authentication_before_pool_access(
    access_policy_config, monkeypatch, caplog
):
    class UnusedPool:
        def acquire(self):
            pytest.fail("unauthenticated request acquired a DB connection")

        async def close(self):
            pass

    async def pool(*args, **kwargs):
        return UnusedPool()

    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(server.asyncpg, "create_pool", pool)
    caplog.set_level("INFO", logger="code_crawler.audit")

    async def run():
        async with http_client() as client:
            for header in (
                None,
                "Bearer",
                "Bearer wrong",
                "Basic secret",
                "Bearer bad token",
            ):
                headers = {"accept": "application/json, text/event-stream"}
                if header is not None:
                    headers["authorization"] = header
                response = await client.post(
                    "/mcp",
                    headers=headers,
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                )
                assert response.status_code == 401
            result = await call_http(
                client,
                access_policy_config[0]["alice"],
                "get_evidence",
                {"repository_key": "other", "relation_id": ID},
            )
            assert result.status_code == 200
            assert result.json()["result"]["isError"]
            assert "access denied" in result.text
            assert "other" not in result.text
            from uuid import uuid4

            denied_cross = await call_http(
                client,
                access_policy_config[0]["alice"],
                "trace_cross_repository",
                {
                    "repository_key": "app",
                    "entity_id": ID,
                    "context": {
                        "mode": "LATEST_INDEXED",
                        "selections": [
                            {
                                "repository_key": "other",
                                "repository_id": str(uuid4()),
                                "snapshot_id": str(uuid4()),
                                "generation": None,
                                "commit_hash": "fixture",
                            }
                        ],
                    },
                },
            )
            assert "access denied" in denied_cross.text
            assert "other" not in denied_cross.text

    asyncio.run(run())
    events = [
        json.loads(r.message) for r in caplog.records if r.name == "code_crawler.audit"
    ]
    assert any(e["operation"] == "http_authenticate" for e in events)
    assert any(e["principal"] == "alice" and not e["allowed"] for e in events)
    assert all(token not in caplog.text for token in access_policy_config[0].values())


def test_direct_tool_call_without_identity_denied(access_policy_config, monkeypatch):
    from test_server import FakePool

    async def pool(*args, **kwargs):
        return FakePool()

    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(server.asyncpg, "create_pool", pool)

    async def run():
        async with Client(server.mcp) as client:
            with pytest.raises(ToolError, match="access denied"):
                await client.call_tool(
                    "get_evidence", {"repository_key": "app", "relation_id": ID}
                )

    asyncio.run(run())


def test_direct_source_evidence_denies_before_reader(access_policy_config, monkeypatch):
    tokens, policy_json = access_policy_config
    policy_json["principals"][0]["permissions"] = ["read"]
    monkeypatch.setenv("MCP_ACCESS_POLICY", json.dumps(policy_json))

    async def run():
        for token, repo in (
            (None, "app"),
            (tokens["alice"], "other"),
            (tokens["alice"], "app"),
        ):
            credential = (
                AccessToken(token=token, client_id="forged-bob", scopes=["source"])
                if token
                else None
            )
            with pytest.raises(PermissionError, match="access denied"):
                await authorized_evidence(None, load_policy(), credential, repo, ID)

    asyncio.run(run())


@pytest.mark.parametrize(
    "tool,args",
    [
        ("search_symbols", {"repository_key": "app", "name": "A"}),
        ("get_evidence", {"repository_key": "app", "relation_id": ID}),
        ("search_discovery_entries", {"kind": "SYMBOL", "lookup_key": "A"}),
    ],
)
def test_membership_without_operation_is_denied(
    access_policy_config, monkeypatch, tool, args
):
    tokens, policy = access_policy_config
    policy["principals"][0]["permissions"] = []
    monkeypatch.setenv("MCP_ACCESS_POLICY", json.dumps(policy))
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")

    class UnusedPool:
        def acquire(self):
            pytest.fail("operation denial reached the database")

        async def close(self):
            pass

    async def pool(*args, **kwargs):
        return UnusedPool()

    monkeypatch.setattr(server.asyncpg, "create_pool", pool)

    async def run():
        async with http_client() as client:
            denied = await call_http(client, tokens["alice"], tool, args)
            assert "access denied" in denied.text

    asyncio.run(run())
