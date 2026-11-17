import asyncio

import asyncpg
import pytest

from code_crawler import transaction_benchmark

pytestmark = pytest.mark.integration


def test_benchmark_uses_private_database_and_cleans_on_failure(
    database_url, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            before = await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_transaction_%'"
            )
            report = await transaction_benchmark.benchmark(database_url, groups=1)
            assert report["files"] == 4 and report["entity_count"] > 100
            assert (
                report["analysis_calls"] == 1
                and report["analysis_calls_in_transaction"] == 0
            )
            assert report["spool_bytes"] > 0 and report["validated"]
            assert report["write_transaction_seconds"] > 0
            assert len(report["canonical_digest"]) == 64

            async def fail(*args, **kwargs):
                raise RuntimeError("injected index failure")

            monkeypatch.setattr(transaction_benchmark, "index_incremental", fail)
            with pytest.raises(RuntimeError, match="injected index failure"):
                await transaction_benchmark.benchmark(database_url, groups=1)
            assert before == await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_transaction_%'"
            )
            assert await conn.fetchval("SELECT to_regclass('ucm_entities')") is None
        finally:
            await conn.close()

    asyncio.run(run())
