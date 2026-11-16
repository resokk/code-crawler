import asyncio
import json
from pathlib import Path

import asyncpg
import pytest

from code_crawler.bulk_benchmark import benchmark
from code_crawler.publication import validate_snapshot
from code_crawler.query_benchmark import plan_nodes

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("locale", ["C", "en_US.utf8"])
def test_bulk_benchmark_validates_publishes_and_cleans_owned_database(
    database_url: str,
    locale: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            before = await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_bulk_%'"
            )
            report = await benchmark(
                database_url,
                pairs=10,
                repeats=2,
                chunk_size=2,
                locale=locale,
                output_path=tmp_path / "complete.json",
            )
            assert json.loads((tmp_path / "complete.json").read_text()) == report
            assert report["complete"]
            assert report["settings"]["lc_collate"] == locale
            assert len(report["trials"]) == 2
            for trial in report["trials"]:
                assert trial["entities"] == 21
                assert (
                    trial["total_seconds"]
                    >= trial["ingest_seconds"] + trial["validation_seconds"]
                )
                assert trial["sql_calls"]["constraints"] == 1
                assert trial["sql_seconds"]["copy"] > 0
                assert trial["sql_seconds"]["insert_select"] > 0
                assert trial["sql_seconds"]["analyze"] > 0
                assert trial["stage_peak_bytes"] > 0
                assert trial["budget_passed"]
            assert await conn.fetchval("SELECT to_regclass('ucm_entities')") is None
            assert before == await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_bulk_%'"
            )

            validations = 0

            async def fail(*args: object, **kwargs: object) -> int:
                nonlocal validations
                validations += 1
                if validations == 2:
                    raise RuntimeError("injected validation failure")
                return await validate_snapshot(*args, **kwargs)

            monkeypatch.setattr("code_crawler.bulk_benchmark.validate_snapshot", fail)
            with pytest.raises(RuntimeError, match="injected validation failure"):
                await benchmark(
                    database_url,
                    pairs=1,
                    repeats=2,
                    locale=locale,
                    output_path=tmp_path / "incomplete.json",
                )
            checkpoint = json.loads((tmp_path / "incomplete.json").read_text())
            assert not checkpoint["complete"]
            assert checkpoint["requested_trials"] == 2
            assert len(checkpoint["trials"]) == 1
            assert checkpoint["trials"][0]["entities"] == 3
            assert before == await conn.fetchval(
                "SELECT count(*) FROM pg_database WHERE datname LIKE 'crawler_bulk_%'"
            )
        finally:
            await conn.close()

    asyncio.run(scenario())


def test_bulk_fk_lookup_uses_entity_id_after_initial_load(database_url: str) -> None:
    async def scenario() -> None:
        report = await benchmark(database_url, pairs=1500, repeats=1, chunk_size=100)
        trial = report["trials"][0]
        indexes = [
            node
            for node in plan_nodes(trial["fk_plan"][0]["Plan"])
            if "Index Cond" in node
        ]
        assert indexes
        assert any("entity_id =" in node["Index Cond"] for node in indexes)
        assert not any(
            node["Node Type"] == "Seq Scan"
            for node in plan_nodes(trial["fk_plan"][0]["Plan"])
        )

    asyncio.run(scenario())
