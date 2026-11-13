import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import pytest

from code_crawler import db, indexer, repos

pytestmark = pytest.mark.integration


async def initialize(conn: asyncpg.Connection) -> None:
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")


def test_migrations_initialize_and_repeat(database_url: str) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            with pytest.raises(RuntimeError, match="не инициализирована"):
                await db.schema_state(conn)
            await initialize(conn)
            assert await db.schema_state(conn) == ([], [])
            assert await conn.fetchval("SELECT count(*) FROM schema_migrations") == len(
                db.migration_names()
            )
            await initialize(conn)
            assert await conn.fetchval("SELECT to_regclass('data_refs')") == "data_refs"
            await conn.execute(
                "INSERT INTO schema_migrations(name) VALUES ('9999_unknown.sql')"
            )
            with pytest.raises(RuntimeError, match="новее кода"):
                await db.begin_migration(conn)
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_failed_migration_rolls_back(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await initialize(conn)
            previous = await conn.fetchval("SELECT count(*) FROM schema_migrations")
            name = "9999_broken.sql"
            (tmp_path / name).write_text(
                "CREATE TABLE rollback_probe(id int); SELECT missing_column;"
            )
            monkeypatch.setattr(db, "MIGRATIONS_DIR", tmp_path)
            with pytest.raises(RuntimeError, match=name):
                await db.apply_migration(conn, name)
            assert await conn.fetchval("SELECT to_regclass('rollback_probe')") is None
            assert (
                await conn.fetchval("SELECT count(*) FROM schema_migrations")
                == previous
            )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_copy_replacement_and_rollback(database_url: str, tmp_path: Path) -> None:
    (tmp_path / "A.java").write_text(
        'class A { void m() { run("select id from users"); } }'
    )
    graph = indexer.build(tmp_path, ["A.java"], lambda: None)

    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            await initialize(conn)
            repo = await indexer.register(conn, "app", "fixture", str(tmp_path))
            other = await indexer.register(conn, "other", "other", str(tmp_path))
            await indexer.store(conn, other, graph, "other-commit", "main")
            await indexer.store(conn, repo, graph, "first", "main")
            assert await conn.fetchval("SELECT count(*) FROM edges") == 2 * len(
                graph.edges
            )
            assert await conn.fetchval("SELECT count(*) FROM data_refs") == 2 * len(
                graph.refs
            )
            assert (
                await conn.fetchval(
                    "SELECT attrs->>'text' FROM nodes WHERE repo_id=$1 AND kind='sql_query'",
                    repo,
                )
                == "select id from users"
            )
            before = await conn.fetch(
                "SELECT * FROM nodes WHERE repo_id=$1 ORDER BY id", repo
            )
            bad = indexer.Graph(nodes=[(None, "bad", "bad", None, None, None, {})])
            with pytest.raises(asyncpg.NotNullViolationError):
                await indexer.store(conn, repo, bad, "broken", "main")
            assert (
                await conn.fetch(
                    "SELECT * FROM nodes WHERE repo_id=$1 ORDER BY id", repo
                )
                == before
            )
            assert (
                await conn.fetchval("SELECT commit_hash FROM repos WHERE id=$1", repo)
                == "first"
            )
            await indexer.store(conn, repo, indexer.Graph(), "second", "main")
            assert (
                await conn.fetchval("SELECT count(*) FROM nodes WHERE repo_id=$1", repo)
                == 0
            )
            assert await conn.fetchval("SELECT count(*) FROM edges") == len(graph.edges)
            assert await conn.fetchval("SELECT count(*) FROM data_refs") == len(
                graph.refs
            )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_cli_db_and_local_index(database_url: str, tmp_path: Path) -> None:
    async def command(*args: str) -> tuple[int, str]:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "from code_crawler.cli import main; main()",
            *args,
            env={**os.environ, "DATABASE_URL": database_url, "NO_COLOR": "1"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=30)
        return process.returncode, output.decode()

    async def scenario() -> None:
        code, output = await command("db", "status")
        assert code == 1 and "не инициализирована" in output
        for args in [
            ("db", "init"),
            ("db", "init"),
            ("db", "migrate"),
            ("db", "status"),
        ]:
            code, output = await command(*args)
            assert code == 0, output
        await repos.git("init", cwd=tmp_path)
        await repos.git("config", "user.name", "Integration", cwd=tmp_path)
        await repos.git("config", "user.email", "test@example.invalid", cwd=tmp_path)
        (tmp_path / "A.java").write_text("class A { void m() {} }")
        await repos.git("add", "A.java", cwd=tmp_path)
        await repos.git("commit", "-m", "fixture", cwd=tmp_path)
        for _ in range(2):
            code, output = await command("index", str(tmp_path))
            assert code == 0, output
        conn = await asyncpg.connect(database_url)
        try:
            assert await conn.fetchval("SELECT count(*) FROM repos") == 1
            assert await conn.fetchval("SELECT count(*) FROM nodes") == 3
            assert (
                await conn.fetchval("SELECT commit_hash FROM repos")
                == (await repos.head(tmp_path))[0]
            )
        finally:
            await conn.close()

    asyncio.run(scenario())
