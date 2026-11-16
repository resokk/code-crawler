import asyncio
from contextlib import asynccontextmanager

import asyncpg
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from code_crawler import search
from code_crawler.server import mcp

ID = "ucm:" + "a" * 64


class FakePool:
    """Stands in for asyncpg: tools are wired to search functions patched per test."""

    def __init__(self) -> None:
        self.transactions: list[tuple[bool, str]] = []

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self, *, readonly: bool, isolation: str):
        self.transactions.append((readonly, isolation))
        yield

    async def close(self) -> None:
        pass


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch, mcp_credentials) -> FakePool:
    fake = FakePool()

    async def create_pool(url: str, **options):
        return fake

    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.delenv("DISCOVERY_REPOSITORY_KEYS", raising=False)
    monkeypatch.setattr(asyncpg, "create_pool", create_pool)
    return fake


def test_server_exposes_structural_tools(pool: FakePool) -> None:
    async def list_tools() -> list:
        async with Client(mcp) as client:
            return await client.list_tools()

    tools = {tool.name: tool for tool in asyncio.run(list_tools())}
    assert set(tools) == {
        "search_discovery_entries",
        "search_symbols",
        "search_text",
        "find_callers",
        "find_callees",
        "find_sql_executions",
        "find_table_readers",
        "find_table_writers",
        "trace_dependency",
        "trace_cross_repository",
        "get_evidence",
    }
    assert all(tool.description for tool in tools.values())
    assert all(
        "principal" not in tool.input_schema["properties"] for tool in tools.values()
    )
    assert "ctx" not in tools["find_callers"].input_schema["properties"]


def test_tool_passes_arguments_reads_only_and_reports_errors(
    pool: FakePool, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    async def find_callers(conn, repository_key, symbol_id, *, limit):
        calls.append((conn, repository_key, symbol_id, limit))
        if repository_key == "missing":
            raise ValueError("repository has no published snapshot")
        return {"snapshot_id": "s", "items": [], "truncated": False}

    monkeypatch.setattr(search, "find_callers", find_callers)

    async def run() -> None:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "find_callers", {"repository_key": "app", "symbol_id": ID, "limit": 7}
            )
            assert result.data == {"snapshot_id": "s", "items": [], "truncated": False}
            with pytest.raises(ToolError, match="query failed"):
                await client.call_tool(
                    "find_callers", {"repository_key": "missing", "symbol_id": ID}
                )
            for bad in (
                {"repository_key": "app", "symbol_id": "not-an-id"},
                {"repository_key": "app", "symbol_id": ID, "limit": 100000},
                {"repository_key": "", "symbol_id": ID},
            ):
                with pytest.raises(ToolError):
                    await client.call_tool("find_callers", bad)

    asyncio.run(run())
    assert calls == [(pool, "app", ID, 7), (pool, "missing", ID, 50)]
    assert pool.transactions == [(True, "repeatable_read"), (True, "repeatable_read")]


def test_discovery_fails_closed_without_policy(pool: FakePool) -> None:
    async def run():
        async with Client(mcp) as client:
            with pytest.raises(ToolError, match="access denied"):
                await client.call_tool(
                    "search_discovery_entries",
                    {"kind": "SYMBOL", "lookup_key": "app.A"},
                )

    asyncio.run(run())


def test_discovery_passes_server_policy_and_client_narrowing(
    pool: FakePool, monkeypatch: pytest.MonkeyPatch
) -> None:
    received = []
    monkeypatch.setenv("DISCOVERY_REPOSITORY_KEYS", '["one","two"]')

    async def find(conn, kind, lookup_key, **options):
        received.append((kind, lookup_key, options))
        return {"items": [], "resolution": "UNRESOLVED"}

    monkeypatch.setattr(search, "search_discovery_entries", find)

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_discovery_entries",
                {"kind": "SYMBOL", "lookup_key": "app.A", "repository_keys": ["one"]},
            )
            assert result.data["resolution"] == "UNRESOLVED"

    asyncio.run(run())
    assert received[0][2]["allowed_repository_keys"] == ["one", "two"]
    assert received[0][2]["repository_keys"] == ["one"]
    assert pool.transactions == [(True, "repeatable_read")]


def test_cross_repository_tool_uses_server_grants(pool, monkeypatch):
    from uuid import uuid4

    from code_crawler.resolver_context import ResolverContext, Selection

    context = ResolverContext(
        mode="LATEST_INDEXED",
        selections=(
            Selection(
                repository_key="repo",
                repository_id=uuid4(),
                snapshot_id=uuid4(),
                generation=None,
                commit_hash="fixture",
            ),
        ),
    )
    monkeypatch.setenv("DISCOVERY_REPOSITORY_KEYS", '["repo"]')
    calls = []

    async def trace(conn, repository_key, entity_id, selected, **options):
        assert selected == context
        calls.append(options)
        raise PermissionError("private repository secret must not escape")

    monkeypatch.setattr(search, "trace_cross_repository", trace)

    async def run():
        async with Client(mcp) as client:
            with pytest.raises(ToolError, match="query failed"):
                await client.call_tool(
                    "trace_cross_repository",
                    {
                        "repository_key": "repo",
                        "entity_id": ID,
                        "context": context.model_dump(mode="json"),
                    },
                )

    asyncio.run(run())
    assert calls[0]["allowed_repositories"] == frozenset(("repo",))
    assert pool.transactions == [(True, "repeatable_read")]


def test_database_qualified_access_tool_contract_and_acl(pool: FakePool, monkeypatch):
    calls = []

    async def find(conn, repository_key, table=None, **options):
        calls.append((repository_key, table, options))
        return {
            "mode": options["mode"],
            "snapshot_id": "s",
            "items": [],
            "truncated": False,
        }

    monkeypatch.setattr(search, "find_table_readers", find)
    monkeypatch.setattr(search, "find_table_writers", find)

    async def run():
        async with Client(mcp) as client:
            for tool in ("find_table_readers", "find_table_writers"):
                by_id = await client.call_tool(
                    tool,
                    {
                        "repository_key": "app",
                        "mode": "RESOLVED_DATABASE_OBJECT",
                        "database_object_id": ID,
                    },
                )
                assert by_id.data["mode"] == "RESOLVED_DATABASE_OBJECT"
                await client.call_tool(
                    tool,
                    {
                        "repository_key": "app",
                        "table": "Users",
                        "column": "ID",
                        "schema": "public",
                        "mode": "RESOLVED_DATABASE_OBJECT",
                        "database_key": "db1",
                        "schema_version_key": "v1",
                        "limit": 7,
                    },
                )
                await client.call_tool(
                    tool, {"repository_key": "app", "table": "users"}
                )
                with pytest.raises(ToolError, match="access denied"):
                    await client.call_tool(
                        tool,
                        {
                            "repository_key": "private",
                            "mode": "RESOLVED_DATABASE_OBJECT",
                            "database_object_id": ID,
                        },
                    )
                for invalid in (
                    {"mode": "EXACT"},
                    {
                        "mode": "RESOLVED_DATABASE_OBJECT",
                        "database_object_id": "db:" + "a" * 64,
                    },
                ):
                    with pytest.raises(ToolError):
                        await client.call_tool(
                            tool, {"repository_key": "app", **invalid}
                        )

    asyncio.run(run())
    assert len(calls) == 6
    assert all(call[0] == "app" for call in calls)
    assert calls[0][1] is None and calls[0][2]["database_object_id"] == ID
    assert calls[1][1] == "Users" and calls[1][2]["database_key"] == "db1"
    assert calls[1][2]["schema_version_key"] == "v1" and calls[1][2]["limit"] == 7
    assert calls[2][2]["mode"] == "SYNTACTIC_NAME"
    assert pool.transactions == [(True, "repeatable_read")] * 6
