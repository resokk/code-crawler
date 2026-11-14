"""Run actual policy hooks in isolated pytest subprocesses, outside the main suite."""

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture
def policy_session(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> pytest.Pytester:
    for name in ("CI", "GITHUB_ACTIONS", "TEST_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    pytester.makepyfile(
        ci_postgres=Path(__file__).with_name("ci_postgres.py").read_text()
    )
    pytester.makeconftest("pytest_plugins = ['ci_postgres']")
    pytester.makeini(
        "[pytest]\nmarkers = integration: PostgreSQL integration coverage\n"
    )
    return pytester


@pytest.mark.parametrize("mode", ["flag", "CI", "GITHUB_ACTIONS"])
def test_mandatory_mode_rejects_missing_database(policy_session, monkeypatch, mode):
    policy_session.makepyfile(
        "import pytest\n@pytest.mark.integration\ndef test_database(): pass\n"
    )
    arguments = []
    if mode == "flag":
        arguments = ["--require-postgres"]
    else:
        monkeypatch.setenv(mode, "true")
    result = policy_session.runpytest_subprocess(*arguments)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(
        ["*mandatory PostgreSQL tests require TEST_DATABASE_URL*"]
    )


def test_local_fixture_can_skip_without_database(policy_session):
    fixture_code = (
        Path(__file__).with_name("integration").joinpath("conftest.py").read_text()
    )
    policy_session.makeconftest(fixture_code + "\npytest_plugins = ['ci_postgres']\n")
    policy_session.makepyfile(
        "import pytest\n@pytest.mark.integration\ndef test_database(database_url): pass\n"
    )
    result = policy_session.runpytest_subprocess()
    result.assert_outcomes(skipped=1)
    assert result.ret == pytest.ExitCode.OK


@pytest.mark.parametrize(
    "action", ["pytest.skip('unavailable')", "pytest.xfail('known defect')"]
)
def test_mandatory_integration_skip_is_failure(policy_session, monkeypatch, action):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://test@localhost/test")
    policy_session.makepyfile(
        f"import pytest\n@pytest.mark.integration\ndef test_database(): {action}\n"
    )
    result = policy_session.runpytest_subprocess("--require-postgres")
    result.assert_outcomes(failed=1)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(
        ["*integration test skipped in mandatory PostgreSQL mode*"]
    )


def test_mandatory_mode_cannot_select_only_unit_tests(policy_session, monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://test@localhost/test")
    policy_session.makepyfile(
        "import pytest\ndef test_unit(): pass\n@pytest.mark.integration\ndef test_database(): pass\n"
    )
    result = policy_session.runpytest_subprocess(
        "--require-postgres", "-m", "not integration"
    )
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(
        ["*mandatory PostgreSQL mode requires selected integration tests*"]
    )


def test_valid_mandatory_selection_allows_unit_only_skips(policy_session, monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://test@localhost/test")
    policy_session.makepyfile(
        "import pytest\ndef test_optional_unit(): pytest.skip('optional')\n@pytest.mark.integration\ndef test_database(): pass\n"
    )
    result = policy_session.runpytest_subprocess()
    result.assert_outcomes(passed=1, skipped=1)
    assert result.ret == pytest.ExitCode.OK


def test_collect_only_cannot_satisfy_mandatory_database_check(
    policy_session, monkeypatch
):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://test@localhost/test")
    policy_session.makepyfile(
        "import pytest\n@pytest.mark.integration\ndef test_database(): pass\n"
    )
    result = policy_session.runpytest_subprocess("--require-postgres", "--collect-only")
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(
        ["*mandatory PostgreSQL mode requires executed integration tests*"]
    )
