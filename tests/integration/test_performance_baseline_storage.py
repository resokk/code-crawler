import asyncio
import json
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest

from code_crawler import search
from code_crawler.performance_baseline import PREFIX, benchmark_suite, run_trial

pytestmark = pytest.mark.integration


def test_baseline_distributions_plans_and_owned_cleanup(database_url, tmp_path):
    async def run():
        admin = await asyncpg.connect(database_url)
        try:
            before = await admin.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_baseline_%'"
            )
            schema = await admin.fetchval(
                "SELECT to_regclass('schema_migrations')::text"
            )
            output = tmp_path / "report.json"
            report = await benchmark_suite(
                database_url,
                output,
                groups=(1,),
                trials=2,
                repeats=2,
                timeout=60,
                gc_timeout=10,
            )
            assert json.loads(output.read_text())["environment"]["implementation_sha"]
            assert report["environment"]["python"]
            assert report["environment"]["uv_lock_sha256"]
            assert len(report["runs"]) == 2
            assert report["distributions_seconds"]["1"]["index"]["count"] == 2
            assert report["runs"][0]["fixture"] == report["runs"][1]["fixture"]
            assert report["runs"][0]["counts"] == report["runs"][1]["counts"]
            for trial in report["runs"]:
                assert trial["status"] == "success", trial.get("failure")
                assert trial["reader_results_unchanged_after_gc"]
                assert trial["entity_count"] > 700
                assert trial["settings"]["work_mem"]
                assert trial["cluster_wal_bytes"] > 0
                assert trial["process"]["peak_rss_kib"] > 0
                assert trial["relation_stats"]
                assert trial["queries"]["callers"]["plans"]
                assert len(trial["queries"]["callers"]["wall_ms"]) == 2
                for stage in (
                    "capture",
                    "prepare",
                    "analyze",
                    "stage",
                    "transfer",
                    "foreign_keys",
                    "archive",
                    "validation",
                    "publication",
                    "clone",
                    "gc",
                ):
                    assert trial["stages"][stage][0]["status"] == "success"
            cancelled = await benchmark_suite(
                database_url,
                output,
                groups=(1,),
                trials=1,
                repeats=1,
                timeout=60,
                gc_timeout=0.000001,
            )
            cancelled_run = cancelled["runs"][0]
            assert cancelled_run["status"] == "failed"
            assert cancelled_run["failure"] == {"type": "TimeoutError", "stage": "gc"}
            assert cancelled_run["reader_results_unchanged_after_gc"]
            timed = await benchmark_suite(
                database_url,
                output,
                groups=(1500,),
                trials=1,
                timeout=0.001,
                gc_timeout=0.001,
            )
            assert timed["runs"][0]["status"] == "timeout"
            assert timed["runs"][0]["returncode"] != 0
            assert before == await admin.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_baseline_%'"
            )
            assert schema == await admin.fetchval(
                "SELECT to_regclass('schema_migrations')::text"
            )
        finally:
            await admin.close()

    asyncio.run(run())


def test_failed_reader_preserves_publication_and_checkpoint(
    database_url, tmp_path, monkeypatch
):
    async def fail(*args, **kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr("code_crawler.performance_baseline._profile", fail)

    async def run():
        admin = await asyncpg.connect(database_url)
        name = PREFIX + uuid4().hex
        await admin.execute(f'CREATE DATABASE "{name}"')
        url = urlunsplit(urlsplit(database_url)._replace(path="/" + name))
        try:
            output = tmp_path / "failure.json"
            report = await run_trial(url, 1, 1, 10, output)
            assert report["status"] == "failed"
            assert report["failure"] == {"type": "RuntimeError", "stage": "readers"}
            assert (
                json.loads(output.read_text())["snapshot_id"] == report["snapshot_id"]
            )
            conn = await asyncpg.connect(url)
            try:
                assert (
                    str(
                        await conn.fetchval(
                            "SELECT snapshot_id FROM ucm_repository_publications"
                        )
                    )
                    == report["snapshot_id"]
                )
                found = await search.search_symbols(conn, "benchmark", "load")
                assert found["items"]
            finally:
                await conn.close()
        finally:
            await admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
            await admin.close()

    asyncio.run(run())
