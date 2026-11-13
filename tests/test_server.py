import asyncio

from fastmcp import Client

from code_crawler.server import mcp


def test_server_has_no_tools() -> None:
    async def list_tools() -> list:
        async with Client(mcp) as client:
            return await client.list_tools()

    assert asyncio.run(list_tools()) == []
