import asyncio

import pytest

from code_crawler import search_projection, search_storage


def test_adaptive_context_pages_preserve_order_and_reject_oversized_single_root(
    monkeypatch,
):
    async def context(conn, snapshot, ids):
        if len(ids) > 1 or ids == ["oversized"]:
            raise search_projection.ProjectionBudgetError("fixture budget")
        return ()

    monkeypatch.setattr(search_projection, "_neighborhood", context)

    async def collect(ids):
        return [
            ids async for ids, _ in search_projection._bounded_pages(None, None, ids)
        ]

    assert asyncio.run(collect(["a", "b", "c"])) == [["a"], ["b"], ["c"]]
    with pytest.raises(search_projection.ProjectionBudgetError):
        asyncio.run(collect(["oversized"]))


def test_copy_byte_budget_splits_records_and_never_truncates(monkeypatch):
    row = ("doc", "id", "TYPE", "{}", "hash", "{}")
    monkeypatch.setattr(search_storage, "_COPY_BYTES", 40)
    assert list(search_storage._copy_chunks([row] * 3)) == [[row, row], [row]]
    with pytest.raises(ValueError, match="byte budget"):
        list(search_storage._copy_chunks([row, (*row[:3], "x" * 50, *row[4:])]))


def test_cancellation_joins_redaction_worker_before_returning():
    from threading import Event

    from test_search_documents import entities

    from code_crawler.data_security import DEFAULT_POLICY
    from code_crawler.ingestion import UcmBatch
    from code_crawler.ucm import Symbol

    facts = entities()
    symbol = next(e for e in facts if isinstance(e, Symbol))
    entered, release = Event(), Event()
    calls = []

    def policy(text):
        calls.append(text)
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return text

    async def run():
        task = asyncio.create_task(
            search_storage._page_records(
                UcmBatch.model_construct(entities=facts),
                policy,
                security_policy=DEFAULT_POLICY,
                report={},
                entity_ids=[symbol.id],
            )
        )
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            await asyncio.sleep(0.01)
            assert not task.done()
            task.cancel()
            await asyncio.sleep(0.01)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            count = len(calls)
            await asyncio.sleep(0.01)
            assert len(calls) == count
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())
