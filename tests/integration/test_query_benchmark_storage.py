import asyncio

import asyncpg
import pytest

from code_crawler.query_benchmark import benchmark

pytestmark = pytest.mark.integration


def test_benchmark_isolated_database_and_identical_results(database_url, monkeypatch):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            before = await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_benchmark_%'"
            )
            report = await benchmark(database_url, groups=1, repeats=1)
            assert report["phases"]["current"]["entity_count"] > 100
            names = {
                r["indexrelname"] for r in report["phases"]["after_0018"]["index_sizes"]
            }
            assert "ucm_entities_symbol_name_idx" in names
            for phase in report["phases"].values():
                assert phase["queries"]["typed_incoming"]["plans"]
                assert phase["queries"]["callers"]["sql_count"] > 0
                assert len(phase["committed_batch_copy_seconds"]) == 2
                assert len(phase["garbage_collection_seconds"]) == 2
            assert (
                await conn.fetchval("SELECT to_regclass('public.schema_migrations')")
                is None
            )
            assert before == await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_benchmark_%'"
            )

            async def fail_query(*args, **kwargs):
                raise RuntimeError("injected benchmark query failure")

            monkeypatch.setattr(
                "code_crawler.query_benchmark.search.search_symbols", fail_query
            )
            with pytest.raises(RuntimeError, match="injected benchmark query failure"):
                await benchmark(database_url, groups=1, repeats=1)
            assert before == await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_benchmark_%'"
            )
        finally:
            await conn.close()

    asyncio.run(run())
