"""Построение графа репозитория и запись его в БД."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg

from code_crawler import java, sql

_NODE_COLUMNS = (
    "id",
    "repo_id",
    "kind",
    "name",
    "qualified_name",
    "file_path",
    "start_line",
    "end_line",
    "attrs",
)


@dataclass
class Graph:
    # (kind, name, qualified_name, file_path, start_line, end_line, attrs)
    nodes: list[tuple] = field(default_factory=list)
    # (индекс узла-источника, индекс узла-цели, kind, attrs)
    edges: list[tuple[int, int, str, dict]] = field(default_factory=list)
    # ссылки на слой данных: (индекс узла, kind, таблица, колонка или None, attrs)
    refs: list[tuple[int, str, str, str | None, dict]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def node(
        self,
        kind: str,
        name: str,
        qualified_name: str,
        file_path: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        attrs: dict | None = None,
    ) -> int:
        self.nodes.append(
            (kind, name, qualified_name, file_path, start_line, end_line, attrs or {})
        )
        return len(self.nodes) - 1

    def count(self, kind: str) -> int:
        return sum(1 for node in self.nodes if node[0] == kind)


def is_indexable(path: str) -> bool:
    return path.endswith(".java")


def build(root: Path, paths: list[str], on_file: Callable[[], None]) -> Graph:
    graph = Graph()
    for path in paths:
        file = root / path
        # Ссылка может вести за пределы репозитория — такие файлы не читаем.
        if file.is_file() and not file.is_symlink():
            try:
                _add_file(graph, path, file.read_bytes())
            # Один плохой файл не должен срывать индекс всего репозитория.
            except Exception as exc:  # noqa: BLE001
                graph.failed.append((path, f"{type(exc).__name__}: {exc}"))
        on_file()
    return graph


def _add_file(graph: Graph, path: str, source: bytes) -> None:
    symbols = java.parse(source)
    file_id = graph.node(
        "file", Path(path).name, path, path, attrs={"language": "java"}
    )
    ids: list[int] = []
    queries: dict[str, int] = {}
    for symbol in symbols:
        symbol_id = graph.node(
            symbol.kind,
            symbol.name,
            symbol.qualified_name,
            path,
            symbol.start_line,
            symbol.end_line,
            symbol.attrs,
        )
        ids.append(symbol_id)
        parent = file_id if symbol.parent is None else ids[symbol.parent]
        graph.edges.append((parent, symbol_id, "contains", {}))
        for query in symbol.queries:
            key = " ".join(query.text.split())
            if key not in queries:
                queries[key] = _add_query(graph, path, query)
            graph.edges.append(
                (symbol_id, queries[key], "executes", {"line": query.line})
            )


def _add_query(graph: Graph, path: str, query: java.Query) -> int:
    analysis = sql.analyze(query.text)
    summary = " ".join(query.text.split())
    query_id = graph.node(
        "sql_query",
        summary[:120],
        f"{path}:{query.line}",
        path,
        query.line,
        query.line,
        {
            "text": query.text,
            "partial": query.partial,
            "parsed": analysis.parsed,
            "operation": analysis.operation,
            "conditions": analysis.conditions,
            "joins": analysis.joins,
            "lineage": analysis.lineage,
            "unresolved_columns": sorted(analysis.unresolved_columns),
        },
    )
    for table, accesses in analysis.tables.items():
        for access in sorted(accesses):
            kind = "reads" if access == "read" else "writes"
            graph.refs.append((query_id, kind, table, None, {"access": access}))
    for (table, column), roles in analysis.columns.items():
        graph.refs.append((query_id, "uses", table, column, {"roles": sorted(roles)}))
    return query_id


async def register(conn: asyncpg.Connection, name: str, source: str, path: str) -> int:
    """Регистрирует репозиторий под именем и возвращает его id."""
    row = await conn.fetchrow("SELECT id, source FROM repos WHERE name = $1", name)
    if row is None:
        return await conn.fetchval(
            "INSERT INTO repos (name, source, path) VALUES ($1, $2, $3) RETURNING id",
            name,
            source,
            path,
        )
    if row["source"] != source:
        raise RuntimeError(
            f"имя {name!r} уже занято репозиторием {row['source']}; "
            "два репозитория с одним именем зарегистрировать нельзя"
        )
    return row["id"]


async def store(
    conn: asyncpg.Connection,
    repo_id: int,
    graph: Graph,
    commit: str,
    branch: str | None,
) -> None:
    """Заменяет индекс репозитория новым графом — целиком, в одной транзакции."""
    async with conn.transaction():
        await conn.execute("DELETE FROM nodes WHERE repo_id = $1", repo_id)
        ids = [
            row[0]
            for row in await conn.fetch(
                "SELECT nextval(pg_get_serial_sequence('nodes', 'id')) "
                "FROM generate_series(1, $1)",
                len(graph.nodes),
            )
        ]
        await conn.copy_records_to_table(
            "nodes",
            columns=_NODE_COLUMNS,
            records=[
                (node_id, repo_id, *node[:-1], json.dumps(node[-1], ensure_ascii=False))
                for node_id, node in zip(ids, graph.nodes, strict=True)
            ],
        )
        await conn.copy_records_to_table(
            "edges",
            columns=("src_id", "dst_id", "kind", "attrs"),
            records=[
                (ids[src], ids[dst], kind, json.dumps(attrs, ensure_ascii=False))
                for src, dst, kind, attrs in graph.edges
            ],
        )
        await conn.copy_records_to_table(
            "data_refs",
            columns=("node_id", "kind", "table_name", "column_name", "attrs"),
            records=[
                (ids[node], kind, table, column, json.dumps(attrs, ensure_ascii=False))
                for node, kind, table, column, attrs in graph.refs
            ],
        )
        await conn.execute(
            "UPDATE repos SET branch = $2, commit_hash = $3, indexed_at = now() WHERE id = $1",
            repo_id,
            branch,
            commit,
        )
