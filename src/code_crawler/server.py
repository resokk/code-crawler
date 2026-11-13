from fastmcp import FastMCP

mcp = FastMCP("code-crawler")


def main() -> None:
    mcp.run(transport="http", stateless_http=True)
