"""Characterization tests: assertions labelled legacy record known defects."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from code_crawler import indexer, java, repos, sql


def test_legacy_unused_sql_is_linked_as_execution(tmp_path: Path) -> None:
    (tmp_path / "A.java").write_text(
        'class A { void m() { String sql = "delete from users"; } }'
    )
    graph = indexer.build(tmp_path, ["A.java"], lambda: None)
    assert graph.count("sql_query") == 1
    assert [
        graph.nodes[src][2] for src, _, kind, _ in graph.edges if kind == "executes"
    ] == ["A.m"]


def test_legacy_constants_leak_between_classes() -> None:
    symbols = java.parse(b"""
        class A {
            static final String TABLE = "first_table";
            void m() { run("select id from " + TABLE); }
        }
        class B {
            static final String TABLE = "second_table";
            void m() { run("select id from " + TABLE); }
        }
    """)
    methods = [symbol for symbol in symbols if symbol.kind == "method"]
    assert [symbol.qualified_name for symbol in methods] == ["A.m", "B.m"]
    assert [[q.text for q in symbol.queries] for symbol in methods] == [
        ["select id from second_table"],
        ["select id from second_table"],
    ]


def test_legacy_overloads_have_identical_names() -> None:
    methods = [
        symbol
        for symbol in java.parse(b"class A { void m(int x) {} void m(String x) {} }")
        if symbol.kind == "method"
    ]
    assert len(methods) == 2
    assert [symbol.qualified_name for symbol in methods] == ["A.m", "A.m"]


def test_legacy_quoted_table_identity_is_folded() -> None:
    quoted = sql.analyze('select id from "Users"')
    ordinary = sql.analyze("select id from users")
    assert quoted.parsed and ordinary.parsed
    assert quoted.tables == ordinary.tables == {"users": {"read"}}


def test_legacy_syntax_error_has_no_diagnostic(tmp_path: Path) -> None:
    (tmp_path / "Broken.java").write_text("class Broken { void m( { }")
    (tmp_path / "Good.java").write_text("class Good { void ok() {} }")
    graph = indexer.build(tmp_path, ["Broken.java", "Good.java"], lambda: None)
    assert graph.failed == []
    assert graph.count("file") == 2
    assert "Good.ok" in {node[2] for node in graph.nodes}


def test_dirty_worktree_indexes_current_tracked_bytes(tmp_path: Path) -> None:
    async def scenario() -> None:
        await repos.git("init", cwd=tmp_path)
        await repos.git("config", "user.name", "Baseline Test", cwd=tmp_path)
        await repos.git(
            "config", "user.email", "baseline@example.invalid", cwd=tmp_path
        )
        source = tmp_path / "A.java"
        source.write_text("class Committed {}")
        await repos.git("add", "A.java", cwd=tmp_path)
        await repos.git("commit", "-m", "fixture", cwd=tmp_path)
        before = await repos.head(tmp_path)
        source.write_text("class Dirty {}")
        (tmp_path / "Untracked.java").write_text("class Untracked {}")
        paths = await repos.files(tmp_path)
        graph = indexer.build(tmp_path, paths, lambda: None)
        assert await repos.head(tmp_path) == before
        assert paths == ["A.java"]
        assert {node[2] for node in graph.nodes} == {"A.java", "Dirty"}
        assert await repos.git("status", "--porcelain", cwd=tmp_path)

    asyncio.run(scenario())


def test_legacy_same_basename_repositories_conflict(tmp_path: Path) -> None:
    first = tmp_path / "one" / "app"
    second = tmp_path / "two" / "app"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    a, b = repos.resolve(str(first)), repos.resolve(str(second))
    assert a.name == b.name == "app"
    conn = AsyncMock()
    conn.fetchrow.return_value = {"id": 1, "source": a.source}
    with pytest.raises(RuntimeError, match="уже занято"):
        asyncio.run(indexer.register(conn, b.name, b.source, str(b.path)))
    conn.fetchval.assert_not_awaited()


def test_dynamic_sql_keeps_partial_marker_and_known_accesses(tmp_path: Path) -> None:
    (tmp_path / "A.java").write_text("""class A {
        void m(String value) {
            run("select id from users where name = " + value);
        }
    }""")
    graph = indexer.build(tmp_path, ["A.java"], lambda: None)
    query = next(node for node in graph.nodes if node[0] == "sql_query")
    assert query[6]["partial"] is True
    assert query[6]["parsed"] is True
    assert query[6]["text"] == "select id from users where name = __unknown__"
    assert {(table, column) for _, _, table, column, _ in graph.refs} == {
        ("users", None),
        ("users", "id"),
        ("users", "name"),
    }
