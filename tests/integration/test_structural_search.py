import asyncio
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from code_crawler import db, repos, search, snapshots
from code_crawler.groovy_adapter import GroovySourceAdapter
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.publication import publish_snapshot, validate_snapshot
from code_crawler.source_adapters import AdapterRegistry, index_sources

pytestmark = pytest.mark.integration

REPO = """package app;
import java.sql.Connection;
import java.sql.PreparedStatement;
public class Repo {
    private final Connection connection;
    public Repo(Connection connection) { this.connection = connection; }
    public void load(String id) throws Exception {
        PreparedStatement ps = connection.prepareStatement("SELECT name, age FROM users WHERE id = ?");
        ps.setString(1, id);
        ps.executeQuery();
    }
    public void save(String name) throws Exception {
        PreparedStatement ps = connection.prepareStatement("UPDATE users SET name = ? WHERE id = 1");
        ps.setString(1, name);
        ps.executeUpdate();
    }
}
"""
SERVICE = """package app;
public class Service {
    private final Repo repo;
    public Service(Repo repo) { this.repo = repo; }
    public void handle(String id) throws Exception { repo.load(id); audit(id); }
    void audit(String id) throws Exception { repo.save(id); }
}
"""


async def publish(conn: asyncpg.Connection, root: Path) -> None:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Search Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    (root / "Repo.java").write_text(REPO)
    (root / "Service.java").write_text(SERVICE)
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    repo = await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key="app", display_name="app", source=str(root)
        ),
    )
    registry = AdapterRegistry(
        (JavaSourceAdapter(profile="orm"), GroovySourceAdapter())
    )
    result = await index_sources(conn, repo, root, registry)
    await validate_snapshot(conn, result.snapshot_id)
    await publish_snapshot(conn, repo, result.snapshot_id, expected_snapshot_id=None)


def test_structural_queries_over_published_snapshot(
    database_url: str, tmp_path: Path
) -> None:
    async def run() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await publish(conn, tmp_path)
            assert {
                r["indexname"]
                for r in await conn.fetch(
                    "SELECT indexname FROM pg_indexes WHERE schemaname='public'"
                )
            } >= {
                "ucm_entities_symbol_name_idx",
                "ucm_relation_candidates_candidate_idx",
                "ucm_sql_executions_owner_idx",
                "ucm_sql_access_names_normalized_idx",
            }
            with pytest.raises(ValueError, match="no published snapshot"):
                await search.search_symbols(conn, "missing", "load")

            async def symbol(name: str) -> str:
                found = await search.search_symbols(conn, "app", name)
                assert len(found["items"]) == 1 and not found["truncated"]
                return found["items"][0]["id"]

            load = await symbol("app.Repo.load")
            handle = await symbol("handle")
            by_signature = await search.search_symbols(
                conn, "app", "load", kind="METHOD", parameter_types=["String"]
            )
            assert by_signature["items"][0]["parameter_types"] == ["String"]
            assert by_signature["items"][0]["path"] == "Repo.java"
            assert not (
                await search.search_symbols(
                    conn, "app", "load", parameter_types=["int"]
                )
            )["items"]
            assert not (await search.search_symbols(conn, "app", "load", kind="CLASS"))[
                "items"
            ]

            callers = await search.find_callers(conn, "app", load)
            (call,) = callers["items"]
            assert call["source"]["qualified_name"] == "app.Service.handle"
            assert call["evidence"] and call["evidence"][0]["path"] == "Service.java"
            assert call["coverage"]["capability"] == "java.calls"
            assert (
                call["coverage"]["status"] == "PARTIAL" and call["coverage"]["reasons"]
            )

            callees = await search.find_callees(conn, "app", handle)
            assert {i["target"]["name"] for i in callees["items"]} == {"load", "audit"}
            # JDBC calls have no target in the repository: reported, never dropped.
            unresolved = (await search.find_callees(conn, "app", load))["items"]
            assert unresolved and all(
                i["resolution"] == "UNRESOLVED" and i["reason"] and i["target"] is None
                for i in unresolved
            )

            executions = await search.find_sql_executions(conn, "app", symbol_id=load)
            (execution,) = executions["items"]
            assert execution["owner"] == "app.Repo.load"
            assert execution["statements"][0]["operation"] == "SELECT"
            assert execution["statements"][0]["relation"]["evidence"]
            assert len((await search.find_sql_executions(conn, "app"))["items"]) == 2

            readers = await search.find_table_readers(conn, "app", "USERS")
            assert {e["owner"] for i in readers["items"] for e in i["executions"]} == {
                "app.Repo.load",
                "app.Repo.save",
            }
            writers = await search.find_table_writers(conn, "app", "users")
            assert {e["owner"] for i in writers["items"] for e in i["executions"]} == {
                "app.Repo.save"
            }
            column = await search.find_table_writers(
                conn, "app", "users", column="name"
            )
            assert [i["object_kind"] for i in column["items"]] == ["COLUMN"]
            assert not (
                await search.find_table_writers(conn, "app", "users", column="age")
            )["items"]
            assert not (await search.find_table_readers(conn, "app", "orders"))["items"]

            trace = await search.trace_dependency(
                conn,
                "app",
                handle,
                relation_kinds=["CALLS", "EXECUTES_SQL", "EXECUTES_STATEMENT"],
                depth=4,
            )
            reached = {
                (i["depth"], i["relation_kind"], (i["target"] or {}).get("name"))
                for i in trace["items"]
            }
            assert {(1, "CALLS", "load"), (2, "CALLS", "save")} <= reached
            assert (4, "EXECUTES_STATEMENT", "UPDATE") in reached
            assert max(i["depth"] for i in trace["items"]) == 4
            shallow = await search.trace_dependency(
                conn, "app", handle, relation_kinds=["CALLS"], depth=1
            )
            assert {i["target"]["name"] for i in shallow["items"]} == {"load", "audit"}
            inward = await search.trace_dependency(
                conn, "app", load, direction="in", relation_kinds=["CALLS"]
            )
            assert [i["source"]["name"] for i in inward["items"]] == ["handle"]
            cut = await search.trace_dependency(conn, "app", handle, depth=3, limit=2)
            assert len(cut["items"]) == 2 and cut["truncated"]

            proof = await search.get_evidence(conn, "app", call["relation_id"])
            assert proof["evidence"] == call["evidence"]
            with pytest.raises(ValueError, match="does not exist"):
                await search.get_evidence(conn, "app", "ucm:" + "0" * 64)
            for bad in ({"limit": 0}, {"limit": search.MAX_LIMIT + 1}, {"depth": 0}):
                with pytest.raises(ValueError):
                    await search.trace_dependency(conn, "app", handle, **bad)
        finally:
            await conn.close()

    asyncio.run(run())


def test_mcp_tool_reads_published_snapshot(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mcp_credentials
) -> None:
    from fastmcp import Client
    from fastmcp.exceptions import ToolError

    from code_crawler.server import mcp

    monkeypatch.setenv("DATABASE_URL", database_url)

    async def run() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await publish(conn, tmp_path)
        finally:
            await conn.close()
        async with Client(mcp) as client:
            found = await client.call_tool(
                "search_symbols", {"repository_key": "app", "name": "app.Repo.save"}
            )
            (symbol,) = found.data["items"]
            writers = await client.call_tool(
                "find_table_writers", {"repository_key": "app", "table": "users"}
            )
            assert {
                e["owner_symbol_id"]
                for i in writers.data["items"]
                for e in i["executions"]
            } == {symbol["id"]}
            callers = await client.call_tool(
                "find_callers", {"repository_key": "app", "symbol_id": symbol["id"]}
            )
            assert callers.data["items"][0]["evidence"]
            with pytest.raises(ToolError, match="query failed"):
                await client.call_tool(
                    "search_symbols", {"repository_key": "missing", "name": "x"}
                )

    asyncio.run(run())


def test_lexical_search_ranks_filters_and_pages(
    database_url: str, tmp_path: Path
) -> None:
    async def run() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await publish(conn, tmp_path)

            async def text(query: str, **options) -> dict:
                return await search.search_text(conn, "app", query, **options)

            def labels(result: dict) -> list[tuple[str, str]]:
                return [
                    (i.get("qualified_name", i["name"]), i["match"])
                    for i in result["items"]
                ]

            assert labels(await text("LOAD"))[0] == ("app.Repo.load", "EXACT")
            assert ("app.Repo.load", "WORDS") in labels(await text("repo load"))
            assert ("app.Service", "SIMILAR") in labels(await text("Servce"))
            assert labels(await text("app.Service.audit"))[0] == (
                "app.Service.audit",
                "EXACT",
            )
            assert not (await text("zzzzqqq"))["items"]
            files = await text("Repo", entity_types=["SOURCE_FILE"])
            assert [i["type"] for i in files["items"]] == ["SOURCE_FILE"]
            assert files["items"][0]["path"] == "Repo.java"

            first = await text("service", limit=1)
            assert first["truncated"] and first["next_offset"] == 1
            second = await text("service", limit=1, offset=first["next_offset"])
            assert second["items"] and second["items"] != first["items"]
            everything = await text("service")
            assert everything["next_offset"] is None
            assert everything["items"][:2] == first["items"] + second["items"]

            published = await conn.fetchval(
                "SELECT snapshot_id FROM ucm_repository_publications"
            )
            pinned = await text("load", snapshot_id=published)
            assert pinned["snapshot_id"] == str(published)
            for bad in (
                {"query": " "},
                {"query": "x", "offset": search.MAX_OFFSET + 1},
                {"query": "x", "entity_types": ["RELATION"]},
                {"query": "x", "snapshot_id": uuid4()},
            ):
                with pytest.raises(ValueError):
                    await search.search_text(conn, "app", **bad)
            # A snapshot that was never published is not readable even by ID.
            building = await snapshots.create_snapshot(
                conn,
                await conn.fetchval("SELECT id FROM ucm_repositories"),
                snapshots.SnapshotInput(
                    commit_hash="c", source_fingerprint="a" * 64, dirty=False
                ),
            )
            with pytest.raises(ValueError, match="not a published version"):
                await text("load", snapshot_id=building)
        finally:
            await conn.close()

    asyncio.run(run())


def test_symbol_hydration_does_not_scan_all_symbols(database_url: str) -> None:
    """A page of results must look symbols up by key, however small the table is."""
    import json

    from test_publication import create, setup

    from code_crawler.ingestion import ingest_stream
    from code_crawler.query_benchmark import RecordingConnection, plan_nodes
    from code_crawler.ucm import EntityType, Symbol, logical_id

    async def run() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn)
            snap = await create(conn, repo)

            async def symbols():
                yield tuple(
                    Symbol(
                        repository_id=str(repo),
                        logical_key=f"java:type:app.C{i}",
                        id=logical_id(
                            str(repo), EntityType.SYMBOL, f"java:type:app.C{i}"
                        ),
                        # Каждое имя встречается 60 раз: страница из 50 результатов.
                        name=f"C{i % 50}",
                        symbol_kind="CLASS",
                        qualified_name=f"app.C{i}",
                    )
                    for i in range(3000)
                )

            await ingest_stream(conn, snap, repo, symbols())
            await validate_snapshot(conn, snap)
            await publish_snapshot(conn, repo, snap, expected_snapshot_id=None)
            await conn.execute("ANALYZE")
            proxy = RecordingConnection(conn)
            for _ in range(7):
                proxy.queries.clear()
                found = await search.search_symbols(proxy, "repo", "C7")
                assert len(found["items"]) == 50 and found["truncated"]
            scans = []
            for query in proxy.queries:
                plan = json.loads(
                    await conn.fetchval(
                        "EXPLAIN (ANALYZE, FORMAT JSON) " + query.sql, *query.arguments
                    )
                )[0]
                scans += [
                    node
                    for node in plan_nodes(plan["Plan"])
                    if node.get("Relation Name") == "ucm_symbols"
                ]
            assert scans
            assert not [
                (
                    node["Relation Name"],
                    node.get("Filter"),
                    node.get("Parent Relationship"),
                )
                for node in scans
                if node["Node Type"] == "Seq Scan"
            ]
        finally:
            await conn.close()

    asyncio.run(run())
