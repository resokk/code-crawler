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


def test_disk_guard_recognizes_only_direct_baseline_workers():
    from code_crawler.performance_baseline_guard import worker_command

    command = [
        "python",
        "-m",
        "code_crawler.performance_baseline",
        "--worker",
        "--groups",
        "199",
    ]
    assert worker_command(command, 42, 42)
    assert not worker_command(command, 43, 42)
    assert not worker_command(command[:3], 42, 42)
    assert not worker_command(
        ["python", "-m", "another.module", "--worker", "--groups", "199"], 42, 42
    )


def test_disk_reserve_stop_is_recorded_and_targets_only_worker(tmp_path, monkeypatch):
    import json
    import signal
    from types import SimpleNamespace

    from code_crawler import performance_baseline_guard as guard

    calls = []
    worker = {"pid": 43, "groups": 1500, "checkpoint": "owned/trial.json"}

    def kill(pid, sent_signal):
        calls.append((pid, sent_signal))
        if calls.count((42, 0)) == 2:
            raise ProcessLookupError

    async def no_delay(seconds):
        pass

    monkeypatch.setattr(guard.os, "kill", kill)
    monkeypatch.setattr(guard, "observe", lambda parent: [worker])
    monkeypatch.setattr(
        guard.shutil, "disk_usage", lambda path: SimpleNamespace(free=100)
    )
    monkeypatch.setattr(guard.asyncio, "sleep", no_delay)
    output = tmp_path / "guard.json"
    asyncio.run(guard.supervise(42, tmp_path, 200, output))
    assert calls == [(42, 0), (43, signal.SIGTERM), (42, 0)]
    report = json.loads(output.read_text())
    assert report["minimum_observed_free_bytes"] == 100
    assert report["events"][0]["signal"] == "SIGTERM"
    assert report["events"][0]["groups"] == 1500


def test_interrupted_index_slice_totals_are_not_complete_scale_samples():
    from code_crawler.performance_baseline import stage_distributions

    success = {"status": "success", "seconds": 1}
    run = {
        "groups": 1500,
        "active_stages": ["index", "transfer"],
        "stages": {
            "capture": [success],
            "prepare": [success],
            "analyze": [success],
            "transfer": [success],
        },
    }
    partial = stage_distributions([run], (1500,))["1500"]
    assert partial["capture"]["count"] == partial["prepare"]["count"] == 1
    assert partial["analyze"]["count"] == partial["transfer"]["count"] == 0
    run["active_stages"] = []
    run["stages"]["index"] = [success]
    assert stage_distributions([run], (1500,))["1500"]["analyze"]["count"] == 1
