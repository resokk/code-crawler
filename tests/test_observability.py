import asyncio
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from code_crawler import observability as metrics


def test_fixed_labels_numeric_only_and_errors():
    recorder = metrics.Observation()
    token = metrics._current.set(recorder)
    try:
        with pytest.raises(ValueError, match="private/source"), metrics.span("analyze"):
            raise ValueError("private/source password=secret")
        metrics.cache("HIT")
        metrics.cache("MISS")
        metrics.cache("private/source")
        metrics.response({"items": ["secret"], "truncated": True})
        recorder.query(SimpleNamespace(elapsed=0.02, exception=None, query="secret"))
        with pytest.raises(ValueError, match="unknown operational stage"):
            recorder.counter("private/source")
    finally:
        metrics._current.reset(token)
    assert recorder.counters["analyze"].errors == 1
    assert recorder.counters["search"].rows == 1
    assert recorder.counters["search"].truncated == 1
    assert recorder.counters["search"].cache_hits == 1
    assert recorder.counters["search"].cache_misses == 1
    assert recorder.counters["db"].seconds == 0.02
    assert "secret" not in repr(recorder) and "private" not in repr(recorder)


def test_parallel_tasks_and_persistence_failure_do_not_mask_original(monkeypatch):
    saved = []

    class Connection:
        def query_logger(self, callback):
            return nullcontext()

    async def persist(conn, recorder, repos, *args):
        saved.append((repos, recorder))
        raise RuntimeError("database secret")

    monkeypatch.setattr(metrics, "persist", persist)

    async def worker(repo, failed):
        async with metrics.recording(Connection(), (repo,)):
            with metrics.span("index"):
                await asyncio.sleep(0)
                if failed:
                    raise LookupError("original")

    async def run():
        results = await asyncio.gather(
            worker("one", True), worker("two", False), return_exceptions=True
        )
        assert isinstance(results[0], LookupError) and results[1] is None
        assert metrics._current.get() is None

    asyncio.run(run())
    by_repo = {repos[0]: recorder for repos, recorder in saved}
    assert by_repo["one"].counters["index"].errors == 1
    assert by_repo["two"].counters["index"].errors == 0


@pytest.mark.parametrize("days", [0, 31, True, "7"])
def test_report_rejects_unbounded_windows_before_database_access(days):
    with pytest.raises(ValueError):
        asyncio.run(metrics.report(None, "repo", days=days))
