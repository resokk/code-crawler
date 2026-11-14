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
        self.transactions: list[bool] = []

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self, *, readonly: bool):
        self.transactions.append(readonly)
        yield

    async def close(self) -> None:
        pass


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> FakePool:
    fake = FakePool()

    async def create_pool(url: str, **options):
        return fake

    monkeypatch.setenv("DATABASE_URL", "postgresql://unused")
    monkeypatch.setattr(asyncpg, "create_pool", create_pool)
    return fake


def test_server_exposes_structural_tools(pool: FakePool) -> None:
    async def list_tools() -> list:
        async with Client(mcp) as client:
            return await client.list_tools()

    tools = {tool.name: tool for tool in asyncio.run(list_tools())}
    assert set(tools) == {
        "search_symbols",
        "find_callers",
        "find_callees",
        "find_sql_executions",
        "find_table_readers",
        "find_table_writers",
        "trace_dependency",
        "get_evidence",
    }
    assert all(tool.description for tool in tools.values())
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
            with pytest.raises(ToolError, match="no published snapshot"):
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
    assert pool.transactions == [True, True]
