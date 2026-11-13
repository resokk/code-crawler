import asyncio
import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from code_crawler import repos
from code_crawler.incremental import FileAnalysis, _capture, plan_changes
from code_crawler.ucm import EntityType, SourceFile, logical_id


def file(path: str, text: str = "same", language: str = "java") -> SourceFile:
    return SourceFile(
        repository_id="repo",
        logical_key=path,
        name=path,
        id=logical_id("repo", EntityType.SOURCE_FILE, path),
        path=path,
        language=language,
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def test_transitive_invalidation_and_unrelated_reuse() -> None:
    previous = {
        path: file(path) for path in ["A.java", "B.java", "C.java", "config.json"]
    }
    current = {**previous, "config.json": file("config.json", "changed")}
    plan = plan_changes(
        previous,
        current,
        {("A.java", "B.java"), ("B.java", "config.json")},
        parsed_paths={"A.java", "B.java", "C.java"},
        full_rebuild=False,
    )
    assert plan.changed == ("config.json",)
    assert plan.reanalyze == ("A.java", "B.java")
    assert plan.reused == ("C.java",)


def test_added_deleted_negative_dependencies_and_dependency_cycles() -> None:
    previous = {p: file(p) for p in ("A.java", "B.java", "old.java")}
    current = {p: file(p) for p in ("A.java", "B.java", "new.java", "missing.conf")}
    plan = plan_changes(
        previous,
        current,
        {("A.java", "missing.conf"), ("B.java", "A.java"), ("A.java", "B.java")},
        parsed_paths={"A.java", "B.java", "new.java"},
        full_rebuild=False,
    )
    assert plan.added == ("missing.conf", "new.java")
    assert plan.deleted == ("old.java",)
    assert plan.reanalyze == ("A.java", "B.java", "new.java")


def test_profile_full_rebuild_and_language_changes() -> None:
    before = {"A.java": file("A.java")}
    same = plan_changes(
        before,
        before,
        set(),
        parsed_paths={"A.java"},
        full_rebuild=False,
        git_changed=("A.java",),
    )
    assert same.reanalyze == () and same.reused == ("A.java",)
    assert same.git_changed == ("A.java",)
    full = plan_changes(
        before, before, set(), parsed_paths={"A.java"}, full_rebuild=True
    )
    assert full.reanalyze == ("A.java",)
    changed = plan_changes(
        before,
        {"A.java": file("A.java", language="other")},
        set(),
        parsed_paths={"A.java"},
        full_rebuild=False,
    )
    assert changed.changed == ("A.java",)


@pytest.mark.parametrize(
    "path", ["../A", "/A", "a//b", "./A", "A/", "C:/A", "a\\b", "a\0b"]
)
def test_file_analysis_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        FileAnalysis(path=path)
    with pytest.raises(ValidationError):
        FileAnalysis(path="A.java", dependencies=(path,))


def test_file_analysis_cannot_override_source_file() -> None:
    with pytest.raises(ValidationError):
        FileAnalysis(path="A.java", entities=(file("A.java"),))


def test_capture_preserves_git_paths_and_ignores_untracked_and_symlinks(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        await repos.git("init", cwd=tmp_path)
        await repos.git("config", "user.name", "Test", cwd=tmp_path)
        await repos.git("config", "user.email", "test@example.invalid", cwd=tmp_path)
        tracked = " space\nname.java"
        (tmp_path / tracked).write_text("old")
        (tmp_path / "link.java").symlink_to(tmp_path / tracked)
        await repos.git("add", "--", tracked, "link.java", cwd=tmp_path)
        await repos.git("commit", "-m", "fixture", cwd=tmp_path)
        repo = uuid4()
        first = await _capture(tmp_path, repo, {".java": "java"})
        assert [s.file.path for s in first.sources] == [tracked]
        assert not first.dirty
        (tmp_path / "ignored.java").write_text("untracked")
        (tmp_path / tracked).write_text("new")
        changed = await _capture(tmp_path, repo, {".java": "java"})
        assert changed.commit == first.commit
        assert changed.fingerprint != first.fingerprint and changed.dirty
        assert changed.sources[0].content == b"new"
        await repos.git("checkout", "--detach", cwd=tmp_path)
        assert (await _capture(tmp_path, repo, {".java": "java"})).branch is None

    asyncio.run(scenario())


def test_capture_does_not_follow_replaced_directory(tmp_path: Path) -> None:
    async def scenario() -> None:
        root = tmp_path / "repo"
        root.mkdir()
        (root / "src").mkdir()
        (root / "src" / "A.java").write_text("original")
        await repos.git("init", cwd=root)
        await repos.git("config", "user.name", "Test", cwd=root)
        await repos.git("config", "user.email", "test@example.invalid", cwd=root)
        await repos.git("add", ".", cwd=root)
        await repos.git("commit", "-m", "fixture", cwd=root)
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "A.java").write_text("outside content")
        (root / "src").rename(root / "saved")
        (root / "src").symlink_to(outside, target_is_directory=True)
        captured = await _capture(root, uuid4(), {".java": "java"})
        assert captured.sources == ()

    asyncio.run(scenario())


def test_capture_rejects_git_conflicts(tmp_path: Path) -> None:
    async def scenario() -> None:
        await repos.git("init", cwd=tmp_path)
        await repos.git("config", "user.name", "Test", cwd=tmp_path)
        await repos.git("config", "user.email", "test@example.invalid", cwd=tmp_path)
        (tmp_path / "A.java").write_text("base\n")
        await repos.git("add", ".", cwd=tmp_path)
        await repos.git("commit", "-m", "fixture", cwd=tmp_path)
        _, original = await repos.head(tmp_path)
        await repos.git("checkout", "-b", "other", cwd=tmp_path)
        (tmp_path / "A.java").write_text("other\n")
        await repos.git("commit", "-am", "other", cwd=tmp_path)
        await repos.git("checkout", original, cwd=tmp_path)
        (tmp_path / "A.java").write_text("original\n")
        await repos.git("commit", "-am", "original", cwd=tmp_path)
        with pytest.raises(RuntimeError):
            await repos.git("merge", "other", cwd=tmp_path)
        with pytest.raises(ValueError, match="conflicts"):
            await _capture(tmp_path, uuid4(), {".java": "java"})

    asyncio.run(scenario())
