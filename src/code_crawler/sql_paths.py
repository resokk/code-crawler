"""Java SQL path settings and opt-in, CLI-owned overflow reporting."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_MAX_PATHS = 256
MAX_PATHS = 65536


def validate_max_paths(value: int) -> int:
    """Reject unbounded or non-integral operator settings before analysis."""
    if type(value) is not int or not 1 <= value <= MAX_PATHS:
        raise ValueError(f"Java SQL max paths must be an integer in 1..{MAX_PATHS}")
    return value


@dataclass(frozen=True)
class PathLimitCase:
    repository_id: str
    path: str
    content_sha256: str
    owner_id: str
    qualified_name: str
    symbol_kind: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    max_paths: int
    attempted_paths_lower_bound: int
    pruning_events: int
    retained_paths: int


@dataclass(frozen=True)
class SqlPathOptions:
    max_paths: int = DEFAULT_MAX_PATHS
    on_method: Callable[[PathLimitCase | None], None] | None = None

    def __post_init__(self) -> None:
        validate_max_paths(self.max_paths)
        if self.on_method is not None and not callable(self.on_method):
            raise ValueError("on_method must be callable")


@dataclass
class PathStats:
    attempted_paths_lower_bound: int = 0
    pruning_events: int = 0
    retained_paths: int = 0


class PathReport:
    """Private metadata spool, safe for concurrent analyzer callbacks."""

    def __init__(
        self, path: Path, root: Path, repository_key: str, max_paths: int
    ) -> None:
        self.path = path.resolve()
        if self.path.is_relative_to(root.resolve()):
            raise ValueError("SQL path report must be outside indexed source root")
        if self.path.exists() and not self.path.is_file():
            raise ValueError("SQL path report target must be a file")
        self.max_paths = validate_max_paths(max_paths)
        self.repository_key = repository_key
        self._stream = tempfile.TemporaryFile(  # noqa: SIM115 - closed by reporting()
            mode="w+", encoding="utf-8", dir=self.path.parent
        )
        self._lock = threading.Lock()
        self._sealed = False
        self._finished = False
        self._methods = 0
        self._cases = 0
        self._metadata: dict = {}

    def record(self, case: PathLimitCase | None) -> None:
        with self._lock:
            if self._sealed:
                return
            self._methods += 1
            if case is not None:
                self._stream.write(
                    json.dumps({"record": "case", **asdict(case)}, sort_keys=True)
                    + "\n"
                )
                self._cases += 1

    def finish(self, status: str, metadata: dict | None = None) -> None:
        """Atomically export completed/failed analysis; no canonical writes here."""
        with self._lock:
            if self._finished:
                return
            self._sealed = True
            self._metadata.update(metadata or {})
            summary = {
                "record": "summary",
                "version": 1,
                "status": status,
                "repository_key": self.repository_key,
                "max_paths": self.max_paths,
                "scope": "reanalyzed_methods_only",
                "analyzed_methods": self._methods,
                "overflow_cases": self._cases,
                **self._metadata,
            }
            self._stream.seek(0)
            name = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self.path.parent,
                    prefix=".sql-paths-",
                    delete=False,
                ) as output:
                    name = output.name
                    output.write(json.dumps(summary, sort_keys=True) + "\n")
                    shutil.copyfileobj(self._stream, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(name, self.path)
                self._finished = True
            finally:
                if name is not None:
                    with suppress(FileNotFoundError):
                        os.unlink(name)

    def close(self) -> None:
        with self._lock:
            self._sealed = True
            with suppress(OSError):
                self._stream.close()


@asynccontextmanager
async def reporting(
    path: str | None, root: Path, repository_key: str, max_paths: int
) -> AsyncIterator[PathReport | None]:
    validate_max_paths(max_paths)
    if path is None:
        yield None
        return
    pending = asyncio.create_task(
        asyncio.to_thread(PathReport, Path(path), root, repository_key, max_paths)
    )
    try:
        report = await asyncio.shield(pending)
    except asyncio.CancelledError:
        with suppress(Exception):
            report = await pending
            await asyncio.to_thread(report.close)
        raise
    try:
        yield report
    except BaseException as error:
        try:
            await asyncio.to_thread(report.finish, "FAILED")
        except Exception as export_error:  # noqa: BLE001 - preserve the original analysis failure
            error.add_note(
                f"SQL path report export failed: {type(export_error).__name__}"
            )
        raise
    else:
        await asyncio.to_thread(report.finish, "ANALYZED")
    finally:
        await asyncio.to_thread(report.close)
