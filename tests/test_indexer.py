from pathlib import Path

import pytest

from code_crawler import indexer, repos


def test_build_links_methods_to_queries_tables_and_columns(tmp_path: Path) -> None:
    (tmp_path / "A.java").write_text(
        'package p; class A { void m() { run("select id from users where name = ?"); }'
        ' void w() { run("delete from users where id = ?"); } }'
    )
    (tmp_path / "broken.java").write_bytes(b"\xff\xfe class {{{")
    (tmp_path / "outside.java").symlink_to(tmp_path.parent)
    seen: list[int] = []

    graph = indexer.build(
        tmp_path, ["A.java", "broken.java", "outside.java"], lambda: seen.append(1)
    )

    assert len(seen) == 3
    assert graph.failed == []
    names = {node[2] for node in graph.nodes}
    assert names == {"A.java", "broken.java", "p.A", "p.A.m", "p.A.w", "A.java:1"}
    links = {
        (graph.nodes[src][2], kind, graph.nodes[dst][2])
        for src, dst, kind, _ in graph.edges
    }
    assert ("A.java", "contains", "p.A") in links
    assert ("p.A", "contains", "p.A.m") in links
    assert ("p.A.m", "executes", "A.java:1") in links
    assert {(kind, table, column) for _, kind, table, column, _ in graph.refs} == {
        ("reads", "users", None),
        ("writes", "users", None),
        ("uses", "users", "id"),
        ("uses", "users", "name"),
    }


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ("git@github.com:org/My-Repo.git", "My-Repo"),
        ("https://host/group/sub/repo2.git/", "repo2"),
        ("ssh://git@host:7999/proj/r3", "r3"),
    ],
)
def test_resolve_extracts_name_from_url(source: str, name: str) -> None:
    repo = repos.resolve(source)

    assert (repo.name, repo.remote, repo.path) == (name, True, repos.REPOS_DIR / name)


def test_resolve_uses_directory_name_for_local_path(tmp_path: Path) -> None:
    repo = repos.resolve(str(tmp_path))

    assert (repo.name, repo.remote, repo.path) == (
        tmp_path.name,
        False,
        tmp_path.resolve(),
    )


@pytest.mark.parametrize("source", ["https://host/..", "--upload-pack=x", "host:"])
def test_resolve_rejects_sources_without_a_plain_name(source: str) -> None:
    with pytest.raises(RuntimeError):
        repos.resolve(source)
