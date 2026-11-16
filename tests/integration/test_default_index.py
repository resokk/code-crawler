import asyncio
from pathlib import Path

import asyncpg
import pytest
from test_publication_cli import command

from code_crawler import cli, db, publication, repos, search, snapshots
from code_crawler.publication import load_snapshot_batch
from code_crawler.reader import published_reader
from code_crawler.ucm import Relation, RelationKind, SqlExecute

pytestmark = pytest.mark.integration

JAVA = """import java.sql.Connection;
import java.sql.PreparedStatement;
class A {
 void helper() {}
 void run(Connection c) {
  helper();
  String unused="DELETE FROM audit_log";
  PreparedStatement p=c.prepareStatement("SELECT id FROM users");
  p.executeQuery();
 }
}
"""


async def migrate(conn):
    for name in await db.begin_migration(conn, init=True):
        await db.apply_migration(conn, name)
    await conn.execute("SELECT pg_advisory_unlock_all()")


async def git_repo(root: Path, text=JAVA):
    root.mkdir(parents=True, exist_ok=True)
    await repos.git("init", cwd=root)
    await repos.git("config", "user.name", "Default Index Test", cwd=root)
    await repos.git("config", "user.email", "test@example.invalid", cwd=root)
    (root / "A.java").write_text(text)
    await repos.git("add", ".", cwd=root)
    await repos.git("commit", "-m", "fixture", cwd=root)


def test_standard_index_publishes_canonical_reuses_and_never_falls_back(
    database_url, tmp_path
):
    async def run():
        conn = await asyncpg.connect(database_url)
        root = tmp_path / "one" / "repo"
        try:
            await migrate(conn)
            await git_repo(root)
            code, output = await command(database_url, "index", str(root))
            assert code == 0 and "PUBLISHED" in output and "ARCHIVED" in output, output
            key = str(root.resolve())
            repo = await conn.fetchval(
                "SELECT id FROM ucm_repositories WHERE repository_key=$1", key
            )
            first = (await snapshots.published_snapshot(conn, repo))["id"]
            assert await conn.fetchval("SELECT count(*) FROM nodes") == 0
            assert await conn.fetchval("SELECT count(*) FROM repos") == 0
            async with published_reader(conn, key) as view:
                run_symbol = (await search.search_symbols(conn, key, "A.run"))["items"][
                    0
                ]["id"]
                assert (
                    await view.get_relations(run_symbol, kinds=(RelationKind.CALLS,))
                ).items
                executions = await search.find_sql_executions(conn, key)
                assert len(executions["items"]) == 1
                dormant = (await search.find_table_writers(conn, key, "audit_log"))[
                    "items"
                ]
                assert dormant and not dormant[0]["executions"]
            code, output = await command(database_url, "index", str(root))
            assert code == 0, output
            second = (await snapshots.published_snapshot(conn, repo))["id"]
            assert second != first
            one = await load_snapshot_batch(conn, first)
            two = await load_snapshot_batch(conn, second)
            assert {e.id: e for e in one.entities} == {e.id: e for e in two.entities}
            (root / "A.java").write_text("class A { void broken( {")
            code, output = await command(database_url, "index", str(root))
            assert code == 1 and "A.java" in output
            assert (await snapshots.published_snapshot(conn, repo))["id"] == second
            assert await conn.fetchval("SELECT count(*) FROM nodes") == 0
            assert (
                await conn.fetchval(
                    "SELECT state FROM ingest_jobs ORDER BY created_at DESC LIMIT 1"
                )
                == "FAILED"
            )
            other = tmp_path / "two" / "repo"
            await git_repo(other, "class B {}")
            code, output = await command(database_url, "index", str(other))
            assert code == 0, output
            assert await conn.fetchval("SELECT count(*) FROM ucm_repositories") == 2
        finally:
            await conn.close()

    asyncio.run(run())


def test_explicit_legacy_warns_and_does_not_promote_unused_sql(database_url, tmp_path):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            await git_repo(tmp_path)
            code, output = await command(
                database_url, "index", str(tmp_path), "--backend", "legacy"
            )
            assert (
                code == 0
                and "LEGACY compatibility" in output
                and "not verified execution" in output
            ), output
            assert (
                await conn.fetchval("SELECT count(*) FROM edges WHERE kind='executes'")
                > 0
            )
            assert await conn.fetchval("SELECT count(*) FROM ucm_snapshots") == 0
            code, output = await command(
                database_url,
                "migrate-index",
                tmp_path.name,
                "--repository-key",
                "legacy-migrated",
            )
            assert code == 0, output
            snapshot = await conn.fetchval(
                "SELECT snapshot_id FROM ucm_repository_publications"
            )
            batch = await load_snapshot_batch(conn, snapshot)
            assert not any(isinstance(e, SqlExecute) for e in batch.entities)
            assert not any(
                isinstance(e, Relation)
                and e.relation_kind
                in (RelationKind.EXECUTES_SQL, RelationKind.EXECUTES_STATEMENT)
                for e in batch.entities
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_remote_file_clone_update_and_wrong_origin_refusal(
    database_url, tmp_path, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            work = tmp_path / "work"
            await git_repo(work, "class A {}")
            bare = tmp_path / "remote.git"
            await repos.git("clone", "--bare", str(work), str(bare))
            monkeypatch.setattr(repos, "REPOS_DIR", tmp_path / "cache")
            monkeypatch.setenv("DATABASE_URL", database_url)
            uri = bare.as_uri()
            await cli.index(uri)
            resolved, key = repos.resolve_canonical(uri)
            assert resolved.path.exists()
            repo = await conn.fetchval(
                "SELECT id FROM ucm_repositories WHERE repository_key=$1", key
            )
            first = (await snapshots.published_snapshot(conn, repo))["id"]
            (work / "A.java").write_text("class A { void newMethod() {} }")
            await repos.git("add", ".", cwd=work)
            await repos.git("commit", "-m", "remote update", cwd=work)
            commit, branch = await repos.head(work)
            await repos.git("push", str(bare), f"HEAD:refs/heads/{branch}", cwd=work)
            await cli.index(uri)
            current = await snapshots.published_snapshot(conn, repo)
            assert current["id"] != first and current["commit_hash"] == commit
            assert (await repos.head(resolved.path))[0] == commit
            await repos.git("config", "user.name", "Cache Test", cwd=resolved.path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=resolved.path
            )
            (resolved.path / "A.java").write_text("class A { void localOnly() {} }")
            await repos.git("add", ".", cwd=resolved.path)
            await repos.git("commit", "-m", "local divergent cache", cwd=resolved.path)
            (work / "A.java").write_text("class A { void remoteOnly() {} }")
            await repos.git("add", ".", cwd=work)
            await repos.git("commit", "-m", "remote divergent update", cwd=work)
            await repos.git("push", str(bare), f"HEAD:refs/heads/{branch}", cwd=work)
            with pytest.raises(SystemExit) as error:
                await cli.index(uri)
            assert error.value.code == 1 and "git pull" in str(error.value.__cause__)
            assert (await snapshots.published_snapshot(conn, repo))["id"] == current[
                "id"
            ]
            await repos.git(
                "remote",
                "set-url",
                "origin",
                "file:///different/repository.git",
                cwd=resolved.path,
            )
            with pytest.raises(SystemExit) as error:
                await cli.index(uri)
            assert error.value.code == 1
            assert (await snapshots.published_snapshot(conn, repo))["id"] == current[
                "id"
            ]
        finally:
            await conn.close()

    asyncio.run(run())


def test_default_index_preserves_publication_on_publish_failure(
    database_url, tmp_path, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            await git_repo(tmp_path)
            monkeypatch.setenv("DATABASE_URL", database_url)
            await cli.index(str(tmp_path), repository_key="explicit")
            repo = await conn.fetchval(
                "SELECT id FROM ucm_repositories WHERE repository_key='explicit'"
            )
            old = (await snapshots.published_snapshot(conn, repo))["id"]

            async def fail_publish(connection, snapshot, expected):
                assert expected == old
                await publication.validate_snapshot(connection, snapshot)
                raise ValueError("injected publication error")

            monkeypatch.setattr(cli, "_publish_cli_snapshot", fail_publish)
            with pytest.raises(SystemExit) as error:
                await cli.index(str(tmp_path), repository_key="explicit")
            assert error.value.code == 1
            assert (await snapshots.published_snapshot(conn, repo))["id"] == old
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_snapshots WHERE state='READY'"
                )
                == 1
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_default_index_requires_current_database_schema(database_url, tmp_path):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await git_repo(tmp_path)
            code, output = await command(database_url, "index", str(tmp_path))
            assert code == 1 and "db init" in output
            assert await conn.fetchval("SELECT to_regclass('ucm_snapshots')") is None
            await migrate(conn)
            await conn.execute(
                "INSERT INTO schema_migrations(name) VALUES ('9999_future.sql')"
            )
            code, output = await command(database_url, "index", str(tmp_path))
            assert code == 1 and "db status" in output
            assert await conn.fetchval("SELECT count(*) FROM ucm_snapshots") == 0
        finally:
            await conn.close()

    asyncio.run(run())
