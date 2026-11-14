from pathlib import Path

import pytest

from code_crawler import repos
from code_crawler.cli import index as original_index


def test_local_identity_is_resolved_path_not_basename(tmp_path: Path):
    a = tmp_path / "one" / "repo"
    b = tmp_path / "two" / "repo"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    ra, ka = repos.resolve_canonical(str(a))
    rb, kb = repos.resolve_canonical(str(b))
    assert not ra.remote and not rb.remote
    assert ka == str(a.resolve()) and ka != kb


def test_remote_namespaces_get_separate_cache_and_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(repos, "REPOS_DIR", tmp_path)
    a, ka = repos.resolve_canonical("git@github.com:one/repo.git")
    b, kb = repos.resolve_canonical("git@github.com:two/repo.git")
    assert a.remote and b.remote and a.path != b.path and ka != kb
    assert a.path.parent == tmp_path and b.path.parent == tmp_path


def test_url_credentials_do_not_enter_identity_or_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(repos, "REPOS_DIR", tmp_path)
    a, ka = repos.resolve_canonical(
        "https://name:secret@example.invalid/team/repo.git?token=private#fragment"
    )
    b, kb = repos.resolve_canonical("https://example.invalid/team/repo.git")
    assert ka == kb == "https://example.invalid/team/repo.git"
    assert a.path == b.path
    assert "secret" not in str(a.path)
    assert a.source.startswith("https://name:secret@")


def test_index_parser_defaults_and_explicit_legacy_options(monkeypatch):
    import asyncio
    import sys

    from code_crawler import cli

    recorded = []

    async def capture(**arguments):
        recorded.append(arguments)

    monkeypatch.setattr(cli, "index", capture)
    monkeypatch.setattr(sys, "argv", ["code-crawler", "index", "source"])
    cli.main()
    assert recorded[0]["backend"] == "ucm"
    assert recorded[0]["java_profile"] is None
    # Invalid compatibility combinations fail before resolving sources or connecting.
    with pytest.raises(SystemExit, match="canonical options"):
        asyncio.run(original_index("source", backend="legacy", java_profile="orm"))
