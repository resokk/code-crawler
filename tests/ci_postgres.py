"""Pytest policy: CI must execute PostgreSQL integration coverage, never skip it."""

import os
from collections.abc import Generator

import pytest

_REQUIRED = pytest.StashKey[bool]()
_EXECUTED = pytest.StashKey[int]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--require-postgres",
        action="store_true",
        help="require configured and selected non-skipped PostgreSQL integration tests",
    )


def pytest_sessionstart(session: pytest.Session) -> None:
    required = session.config.getoption("--require-postgres") or any(
        os.environ.get(name, "").lower() in ("1", "true")
        for name in ("CI", "GITHUB_ACTIONS")
    )
    session.config.stash[_REQUIRED] = required
    session.config.stash[_EXECUTED] = 0
    if required and not os.environ.get("TEST_DATABASE_URL", "").strip():
        raise pytest.UsageError("mandatory PostgreSQL tests require TEST_DATABASE_URL")


def pytest_collection_finish(session: pytest.Session) -> None:
    if session.config.stash[_REQUIRED] and not any(
        item.get_closest_marker("integration") for item in session.items
    ):
        raise pytest.UsageError(
            "mandatory PostgreSQL mode requires selected integration tests"
        )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if report.when == "call" and item.get_closest_marker("integration"):
        item.config.stash[_EXECUTED] += 1
    if (
        item.config.stash[_REQUIRED]
        and report.skipped
        and item.get_closest_marker("integration")
    ):
        report.outcome = "failed"
        report.longrepr = (
            f"integration test skipped in mandatory PostgreSQL mode: {report.longrepr}"
        )
        if hasattr(report, "wasxfail"):
            del report.wasxfail
    return report


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if (
        session.config.stash.get(_REQUIRED, False)
        and exitstatus == pytest.ExitCode.OK
        and not session.config.stash[_EXECUTED]
    ):
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = session.config.pluginmanager.getplugin("terminalreporter")
        if reporter:
            reporter.write_sep(
                "=",
                "mandatory PostgreSQL mode requires executed integration tests",
                red=True,
            )
