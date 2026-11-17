import asyncio
import json

import asyncpg
import pytest

from code_crawler import cli, db, repos, sql_paths

pytestmark = pytest.mark.integration


def test_cli_budget_report_reuse_retry_parameters_and_export_failure(
    database_url, tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_URL", database_url)
    root = tmp_path / "repo"
    root.mkdir()
    report = tmp_path / "paths.jsonl"
    text = "class A { void m(boolean a,boolean b,boolean c){int n=0;if(a){n++;}else{n--;}if(b){n++;}else{n--;}if(c){n++;}else{n--;}}}"
    (root / "A.java").write_text(text)

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=root)
            await repos.git("config", "user.name", "Test", cwd=root)
            await repos.git("config", "user.email", "test@example.invalid", cwd=root)
            await repos.git("add", ".", cwd=root)
            await repos.git("commit", "-m", "fixture", cwd=root)

            async def index(budget, path):
                await cli.index_registered(
                    str(root),
                    "repo",
                    "sql",
                    "postgres",
                    "UNKNOWN",
                    publish=True,
                    java_sql_max_paths=budget,
                    java_sql_path_report=str(path),
                )
                return [json.loads(line) for line in path.read_text().splitlines()]

            first = await index(2, report)
            assert first[0]["status"] == "ANALYZED" and first[0]["overflow_cases"] == 1
            assert first[1]["qualified_name"] == "A.m" and first[1]["max_paths"] == 2
            repository = await conn.fetchval(
                "SELECT id FROM ucm_repositories WHERE repository_key='repo'"
            )
            pointer = await conn.fetchval(
                "SELECT snapshot_id FROM ucm_repository_publications WHERE repository_id=$1",
                repository,
            )
            assert first[0]["snapshot_id"] == str(pointer)
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_sql_constructions WHERE snapshot_id=$1",
                    pointer,
                )
                == 0
            )
            second = await index(2, tmp_path / "second.jsonl")
            assert len(second) == 1 and second[0]["analyzed_methods"] == 0
            assert (
                second[0]["reused_files"] == 1
                and second[0]["scope"] == "reanalyzed_methods_only"
            )
            third = await index(4, tmp_path / "third.jsonl")
            assert third[0]["reanalyzed_files"] == 1 and third[0]["reused_files"] == 0
            assert third[1]["max_paths"] == 4
            pointer = await conn.fetchval(
                "SELECT snapshot_id FROM ucm_repository_publications WHERE repository_id=$1",
                repository,
            )
            parameters = json.loads(
                await conn.fetchval(
                    "SELECT parameters FROM ingest_jobs ORDER BY created_at DESC LIMIT 1"
                )
            )
            assert parameters["java_sql_max_paths"] == 4
            assert parameters["java_sql_path_report"] == str(
                (tmp_path / "third.jsonl").resolve()
            )

            def fail_export(*args, **kwargs):
                raise OSError("injected export failure")

            original_finish = sql_paths.PathReport.finish
            monkeypatch.setattr(sql_paths.PathReport, "finish", fail_export)
            with pytest.raises(SystemExit):
                await index(8, report)
            assert (
                await conn.fetchval(
                    "SELECT snapshot_id FROM ucm_repository_publications WHERE repository_id=$1",
                    repository,
                )
                == pointer
            )
            assert (
                json.loads(report.read_text().splitlines()[0])["snapshot_id"]
                == first[0]["snapshot_id"]
            )
            job = await conn.fetchrow(
                "SELECT id,state,snapshot_id FROM ingest_jobs ORDER BY created_at DESC LIMIT 1"
            )
            assert job["state"] == "FAILED" and job["snapshot_id"] is not None
            monkeypatch.setattr(sql_paths.PathReport, "finish", original_finish)
            await cli.jobs_retry(job["id"])
            retried = await conn.fetchrow(
                "SELECT state,attempt,snapshot_id FROM ingest_jobs WHERE id=$1",
                job["id"],
            )
            assert retried["state"] == "SUCCEEDED" and retried["attempt"] == 2
            replayed = json.loads(report.read_text().splitlines()[0])
            assert replayed["max_paths"] == 8 and replayed["status"] == "ANALYZED"
            assert replayed["snapshot_id"] == str(retried["snapshot_id"])
            assert replayed["overflow_cases"] == 0  # exactly 8 paths
        finally:
            await conn.close()

    asyncio.run(run())
