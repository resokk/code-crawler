import sys
import threading
import time
from collections import Counter
from pathlib import Path

from code_crawler import profiling


def test_sample_keeps_working_threads_and_marks_a_waiting_process() -> None:
    parked = threading.Event()
    release = threading.Event()

    def idle() -> None:
        parked.set()
        release.wait()

    worker = threading.Thread(target=idle)
    worker.start()
    try:
        parked.wait()
        time.sleep(0.05)
        frames = sys._current_frames()
        main = threading.main_thread().ident
        # The main thread is running this test, the worker is parked in Event.wait.
        (stack,) = profiling.sample(frames, main, skip=-1)
        assert stack[-1].endswith(
            ":test_sample_keeps_working_threads_and_marks_a_waiting_process"
        )
        # With the only working thread excluded, the process counts as waiting.
        waiting = profiling.sample({worker.ident: frames[worker.ident]}, main, -1)
        assert waiting == []
        (stack,) = profiling.sample(
            {main: frames[worker.ident], worker.ident: frames[worker.ident]}, main, -1
        )
        assert stack[-1] == profiling.WAITING
    finally:
        release.set()
        worker.join()


def test_summary_counts_inclusive_and_own_shares() -> None:
    stacks = Counter(
        {
            ("asyncio/runners.py:run", "code_crawler/a.py:outer"): 1,
            (
                "code_crawler/a.py:outer",
                "code_crawler/a.py:inner",
                "code_crawler/a.py:inner",
            ): 3,
        }
    )
    assert profiling.summary(stacks) == [
        "   всего   сама  функция (4 замеров)",
        "  100.0%  25.0%  code_crawler/a.py:outer",
        "   75.0%  75.0%  code_crawler/a.py:inner",
    ]


def test_profiled_writes_collapsed_stacks_of_worker_threads(tmp_path: Path) -> None:
    def spin() -> None:
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            sum(range(1000))

    target = tmp_path / "run.prof"
    with profiling.profiled(target) as stacks:
        worker = threading.Thread(target=spin)
        worker.start()
        worker.join()

    assert any(stack[-1].endswith(".<locals>.spin") for stack in stacks)
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(stacks)
    assert all(line.rsplit(" ", 1)[1].isdigit() for line in lines)
