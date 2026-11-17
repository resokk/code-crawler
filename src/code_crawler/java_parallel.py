"""Bounded spawn-only Java analysis using private pipes and public process APIs."""

from __future__ import annotations

import asyncio
import multiprocessing as mp
import os
import threading
import time
from dataclasses import dataclass
from multiprocessing.connection import Connection, wait

from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.sql_paths import SqlPathOptions


def validate_workers(value: int) -> int:
    """Bound explicit process counts; default sequential mode remains one."""
    if type(value) is not int or not 1 <= value <= 32:
        raise ValueError("analysis workers must be an integer in 1..32")
    return value


@dataclass(frozen=True)
class WorkerConfig:
    sources: tuple[SourceInput, ...]
    profile: str
    schemas: tuple
    assignments: tuple
    dialect: str
    naming_policy: str
    max_paths: int
    report_enabled: bool
    expected_version: str


def _worker_main(pipe: Connection, config: WorkerConfig) -> None:
    # Imports/classes are reconstructed in the child; no AST, callback or DB handle
    # is an argument. This pipe accepts only this parent's known captured data.
    from code_crawler.java_adapter import JavaSourceAdapter, _build_analyzer

    observations = []
    try:
        adapter = JavaSourceAdapter(
            profile=config.profile,
            schemas=config.schemas,
            assignments=config.assignments,
            dialect=config.dialect,
            naming_policy=config.naming_policy,
            sql_options=SqlPathOptions(
                config.max_paths, observations.append if config.report_enabled else None
            )
            if config.profile != "calls"
            else None,
        )
        analyzer = _build_analyzer(adapter, config.sources)
        if analyzer.analysis_version != config.expected_version:
            raise ValueError("worker catalogue version does not match parent")
        pipe.send(("ready", None))
        while (paths := pipe.recv()) is not None:
            observations.clear()
            results = tuple(analyzer.analysis(analyzer.files[path]) for path in paths)
            pipe.send(("result", (results, tuple(observations))))
    except BaseException as error:  # noqa: BLE001 - child boundary must notify parent
        try:
            pipe.send(("error", f"{type(error).__name__}: {str(error)[:2048]}"))
        except (OSError, EOFError):
            pass
    finally:
        pipe.close()


def _supervised_worker(pipe: Connection, config: WorkerConfig, target) -> None:
    parent = mp.parent_process()
    if parent is not None:

        def parent_exit():
            wait([parent.sentinel])
            os._exit(1)

        threading.Thread(target=parent_exit, daemon=True).start()
    target(pipe, config)


@dataclass
class _Worker:
    process: mp.Process
    pipe: Connection
    ready: bool = False

    def receive(self, expected: str):
        while True:
            try:
                available = wait([self.pipe, self.process.sentinel], timeout=0.25)
                if available:
                    break
            except (OSError, ValueError) as error:
                raise RuntimeError("Java analysis worker connection closed") from error
        if self.pipe in available:
            try:
                kind, payload = self.pipe.recv()
            except (OSError, EOFError) as error:
                raise RuntimeError(
                    "Java analysis worker exited without a result"
                ) from error
            if kind == expected:
                return payload
            raise RuntimeError(f"Java analysis worker failed: {payload}")
        raise RuntimeError("Java analysis worker exited without a result")

    def request(self, paths: tuple[str, ...]):
        if not self.ready:
            self.receive("ready")
            self.ready = True
        try:
            self.pipe.send(paths)
        except (OSError, EOFError) as error:
            raise RuntimeError("Java analysis worker exited before request") from error
        return self.receive("result")


class JavaProcessPool:
    """One bounded group per worker; never prefetch beyond the current source slice."""

    def __init__(self, config: WorkerConfig, workers: int, *, _target=None) -> None:
        validate_workers(workers)
        self._workers: list[_Worker] = []
        self._pids: list[int] = []
        self._closed = False
        self._close_lock = threading.Lock()
        self._serial = asyncio.Lock()
        context = mp.get_context("spawn")
        try:
            for _ in range(workers):
                parent, child = context.Pipe()
                process = context.Process(
                    target=_supervised_worker,
                    args=(child, config, _target or _worker_main),
                )
                try:
                    process.start()
                except BaseException:
                    parent.close()
                    raise
                finally:
                    child.close()
                self._workers.append(_Worker(process, parent))
                self._pids.append(process.pid)
        except BaseException:
            self.close(abort=True)
            raise

    @property
    def pids(self) -> tuple[int, ...]:
        return tuple(self._pids)

    async def analyze(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[tuple[FileAnalysis, ...], tuple]:
        async with self._serial:
            if self._closed:
                raise RuntimeError("Java analysis pool is closed")
            if not sources:
                return (), ()
            size = -(-len(sources) // len(self._workers))
            groups = [
                tuple(s.file.path for s in sources[start : start + size])
                for start in range(0, len(sources), size)
            ]
            tasks = [
                asyncio.create_task(asyncio.to_thread(worker.request, group))
                for worker, group in zip(self._workers, groups, strict=False)
            ]
            try:
                responses = await asyncio.gather(*tasks)
            except BaseException:
                await self.aclose(abort=True)
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            return (
                tuple(result for batch, _ in responses for result in batch),
                tuple(event for _, events in responses for event in events),
            )

    async def aclose(self, *, abort: bool = False) -> None:
        pending = asyncio.create_task(asyncio.to_thread(self.close, abort=abort))
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            await pending
            raise

    def close(self, *, abort: bool = False) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            for worker in self._workers:
                if abort:
                    if worker.process.is_alive():
                        worker.process.terminate()
                else:
                    try:
                        worker.pipe.send(None)
                    except (OSError, EOFError):
                        pass
            deadline = time.monotonic() + 5
            for worker in self._workers:
                worker.process.join(max(0, deadline - time.monotonic()))
            for worker in self._workers:
                if worker.process.is_alive():
                    worker.process.kill()
                    worker.process.join()
                worker.pipe.close()
                worker.process.close()
