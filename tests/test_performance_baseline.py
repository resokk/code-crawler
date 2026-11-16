import asyncio

import pytest

from code_crawler.performance_baseline import (
    _fixture,
    benchmark_suite,
    distribution,
    run_trial,
)


def test_deterministic_workload_and_sample_distribution(tmp_path):
    first = _fixture(tmp_path / "one", 199)
    second = _fixture(tmp_path / "two", 199)
    assert first == second
    assert first["files"] == 400
    assert _fixture(tmp_path / "three", 499)["files"] == 1000
    assert first["sha256"] != _fixture(tmp_path / "four", 1)["sha256"]
    stats = distribution([3, 1, 2])
    assert stats["samples"] == [3, 1, 2]
    assert stats["median"] == stats["mean"] == 2
    assert stats["stdev"] == 1
    assert distribution([]) == {"samples": [], "count": 0}


@pytest.mark.parametrize(
    "arguments",
    [
        {"groups": ()},
        {"groups": (0,)},
        {"groups": (True,)},
        {"trials": 0},
        {"repeats": 51},
        {"timeout": -1},
        {"gc_timeout": 0},
    ],
)
def test_invalid_workload_fails_before_connect(arguments, tmp_path):
    with pytest.raises(ValueError, match="invalid baseline"):
        asyncio.run(
            benchmark_suite(
                "postgresql://unused.invalid/postgres",
                tmp_path / "report.json",
                **arguments,
            )
        )


def test_worker_rejects_unowned_database_before_connect(tmp_path):
    with pytest.raises(ValueError, match="owned"):
        asyncio.run(
            run_trial(
                "postgresql://unused.invalid/production",
                1,
                1,
                1,
                tmp_path / "report.json",
            )
        )
