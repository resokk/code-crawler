"""Opt-in in-process sampling profiler for CLI commands; see docs/profiling.md."""

import sys
import threading
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import CodeType, FrameType

_INTERVAL = 0.01
WAITING = "[ожидание]"
# A thread parked here is waiting for work, an event or a socket, not computing.
_PACKAGE = Path(__file__).parent
_NAMES: dict[CodeType, str] = {}
_IDLE = {
    ("threading.py", "wait"),
    ("thread.py", "_worker"),
    ("selectors.py", "select"),
}


def _name(code: CodeType) -> str:
    name = _NAMES.get(code)
    if name is None:
        path = Path(code.co_filename)
        # Package files keep their full relative path so the summary can pick them out.
        parts = (
            (_PACKAGE.name, *path.relative_to(_PACKAGE).parts)
            if path.is_relative_to(_PACKAGE)
            else path.parts[-2:]
        )
        name = _NAMES[code] = "/".join(parts) + ":" + code.co_qualname
    return name


def _stack(frame: FrameType | None) -> tuple[str, ...]:
    names = []
    while frame is not None:
        names.append(_name(frame.f_code))
        frame = frame.f_back
    return tuple(reversed(names))


def _idle(frame: FrameType) -> bool:
    code = frame.f_code
    return (Path(code.co_filename).name, code.co_name) in _IDLE


def sample(frames: dict[int, FrameType], main: int, skip: int) -> list[tuple[str, ...]]:
    """Stacks of the threads doing work; the waiting main thread when none is."""
    busy = [
        _stack(frame)
        for ident, frame in frames.items()
        if ident != skip and not _idle(frame)
    ]
    if not busy and main in frames:
        busy = [(*_stack(frames[main]), WAITING)]
    return busy


def summary(stacks: Counter[tuple[str, ...]], limit: int = 25) -> list[str]:
    """Share of samples per code_crawler function: anywhere on the stack and on top."""
    total = sum(stacks.values()) or 1
    inclusive: Counter[str] = Counter()
    own: Counter[str] = Counter()
    for stack, count in stacks.items():
        for name in set(stack):
            inclusive[name] += count
        own[stack[-1]] += count
    rows = [
        f"  {count / total:6.1%} {own[name] / total:6.1%}  {name}"
        for name, count in inclusive.most_common()
        if name.startswith("code_crawler/")
    ]
    return [f"   всего   сама  функция ({total} замеров)", *rows[:limit]]


@contextmanager
def profiled(path: Path) -> Iterator[Counter[tuple[str, ...]]]:
    """Sample every thread of this process until exit, then write collapsed stacks."""
    stacks: Counter[tuple[str, ...]] = Counter()
    done = threading.Event()
    main = threading.main_thread().ident

    def run() -> None:
        while not done.wait(_INTERVAL):
            stacks.update(sample(sys._current_frames(), main, threading.get_ident()))

    sampler = threading.Thread(target=run, name="profiler", daemon=True)
    sampler.start()
    try:
        yield stacks
    finally:
        done.set()
        sampler.join()
        path.write_text(
            "".join(
                f"{';'.join(stack)} {count}\n"
                for stack, count in sorted(stacks.items())
            ),
            encoding="utf-8",
        )
