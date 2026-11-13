import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, indexer, legacy, repos, snapshots

pytestmark = pytest.mark.integration


async def setup(conn: asyncpg.Connection, root: Path) -> int:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Migration Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    (root / "A.java").write_text(
        'class A { void m() { String sql = "delete from users"; } }'
    )
    (root / "test.plp").write_text("begin null; end;")
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)
    repo = await indexer.register(conn, root.name, str(root), str(root))
    await store(conn, root, repo)
    return repo


async def store(conn: asyncpg.Connection, root: Path, repo: int) -> None:
    commit, branch = await repos.head(root)
    paths = [p for p in await repos.files(root) if indexer.is_indexable(p)]
    graph = indexer.build(root, paths, lambda: None)
    await indexer.store(conn, repo, graph, commit, branch)


def test_migrate_compare_switch_read_and_return_to_legacy(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            old_nodes = await conn.fetch("SELECT * FROM nodes ORDER BY id")
            snap = await legacy.migrate_index(conn, tmp_path.name, "org/app")
            report = await legacy.compare_index(conn, "org/app")
            assert report["matches"] and report["limitations"]
            assert str(snap) == report["snapshot_id"]
            assert await conn.fetch("SELECT * FROM nodes ORDER BY id") == old_nodes
            old = await legacy.read_graph(conn, "org/app")
            await legacy.use_index(conn, "org/app", "ucm")
            new = await legacy.read_graph(conn, "org/app")
            assert legacy._payload(old) == legacy._payload(new)
            assert any(kind == "executes" for _, _, kind, _ in new.edges)
            assert not await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM ucm_relations WHERE relation_kind='EXECUTES_SQL')"
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_entities WHERE entity_type='SQL_CANDIDATE'"
                )
                > 0
            )
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "DELETE FROM ingest_legacy_nodes WHERE snapshot_id=$1", snap
                )
            (tmp_path / "A.java").write_text(
                'class Changed { void m() { run("select id from users"); } }'
            )
            await store(conn, tmp_path, repo)
            assert not (await legacy.compare_index(conn, "org/app"))["matches"]
            assert legacy._payload(
                await legacy.read_graph(conn, "org/app")
            ) == legacy._payload(new)
            await legacy.use_index(conn, "org/app", "legacy")
            changed = await legacy.read_graph(conn, "org/app")
            assert legacy._payload(changed) != legacy._payload(new)
            with pytest.raises(ValueError, match="differ"):
                await legacy.use_index(conn, "org/app", "ucm")
            second = await legacy.migrate_index(conn, tmp_path.name, "org/app")
            assert second != snap
            assert (await legacy.compare_index(conn, "org/app"))["matches"]
            await legacy.use_index(conn, "org/app", "ucm")
            assert legacy._payload(
                await legacy.read_graph(conn, "org/app")
            ) == legacy._payload(changed)
        finally:
            await conn.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("problem", ["source_drift", "projection_failure"])
def test_failed_migration_preserves_legacy_and_published_graph(
    database_url: str, tmp_path: Path, problem: str
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await setup(conn, tmp_path)
            old = await legacy.migrate_index(conn, tmp_path.name, "org/app")
            nodes = await conn.fetch("SELECT * FROM nodes ORDER BY id")
            if problem == "source_drift":
                (tmp_path / "A.java").write_text("class Different {}")
            else:
                await conn.execute("""CREATE FUNCTION fail_projection() RETURNS trigger LANGUAGE plpgsql AS $$
                    BEGIN RAISE EXCEPTION 'projection failure' USING ERRCODE='23514'; END; $$;
                    CREATE TRIGGER fail_projection BEFORE INSERT ON ingest_legacy_nodes FOR EACH ROW EXECUTE FUNCTION fail_projection();""")
            with pytest.raises((ValueError, asyncpg.CheckViolationError)):
                await legacy.migrate_index(conn, tmp_path.name, "org/app")
            assert await conn.fetch("SELECT * FROM nodes ORDER BY id") == nodes
            repo = await conn.fetchval(
                "SELECT repository_id FROM ucm_legacy_repositories"
            )
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_entities WHERE snapshot_id<>$1", old
                )
                == 0
            )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_cli_migration_workflow(database_url: str, tmp_path: Path) -> None:
    async def command(*args: str) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "from code_crawler.cli import main; main()",
            *args,
            env={**os.environ, "DATABASE_URL": database_url, "NO_COLOR": "1"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        return proc.returncode, output.decode()

    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await setup(conn, tmp_path)
        finally:
            await conn.close()
        for args in [
            ("migrate-index", tmp_path.name, "--repository-key", "org/app"),
            ("compare-index", "org/app"),
            ("use-index", "org/app", "--backend", "ucm"),
            ("show-index", "org/app"),
            ("use-index", "org/app", "--backend", "legacy"),
        ]:
            code, output = await command(*args)
            assert code == 0, output
        code, output = await command("compare-index", "absent")
        assert code == 1 and "no legacy" in output

    asyncio.run(scenario())


def test_plplus_shared_symbols_calls_and_data_refs_are_preserved(
    database_url: str, tmp_path: Path
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            repo = await setup(conn, tmp_path)
            files = {
                "type/rates/methods/new_auto/src/execute.plp": "begin [CREDIT] := P_CREDIT; end;",
                "type/rates/methods/lib/src/private.plp": """
                    function Calc return number is n number; begin
                      select x(x.[PRC]) in ::[RATES] all into n;
                      n := ::[RATES].[NEW_AUTO](); return n;
                    end;
                """,
            }
            for path, text in files.items():
                (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
                (tmp_path / path).write_text(text)
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "PLPlus fixture", cwd=tmp_path)
            await store(conn, tmp_path, repo)
            await legacy.migrate_index(conn, tmp_path.name, "org/app")
            before = await legacy.read_graph(conn, "org/app")
            assert any(kind == "calls" for _, _, kind, _ in before.edges)
            assert any(table == "z#rates" for _, _, table, _, _ in before.refs)
            assert any(node[0] == "function" for node in before.nodes)
            await legacy.use_index(conn, "org/app", "ucm")
            assert legacy._payload(
                await legacy.read_graph(conn, "org/app")
            ) == legacy._payload(before)
        finally:
            await conn.close()

    asyncio.run(scenario())
