"""Построение графа репозитория и запись его в БД."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg

from code_crawler import java, plp, sql

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
    # узлы, на которые ссылаются по имени: (kind, qualified_name) -> индекс
    named: dict[tuple[str, str], int] = field(default_factory=dict)
    # вызовы по имени, которые связываются с узлами после разбора всех файлов:
    # (индекс вызывающего узла, имя цели по частям, строка)
    calls: list[tuple[int, tuple[str, ...], int]] = field(default_factory=list)
    # возможные вызовы функций по короткому имени: (индекс узла, полное имя функции, строка)
    local_calls: list[tuple[int, str, int]] = field(default_factory=list)

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
    return path.endswith((".java", ".plp"))


def build(root: Path, paths: list[str], on_file: Callable[[], None]) -> Graph:
    graph = Graph()
    for path in paths:
        file = root / path
        # Ссылка может вести за пределы репозитория — такие файлы не читаем.
        if file.is_file() and not file.is_symlink():
            try:
                add = _add_plp_file if path.endswith(".plp") else _add_file
                add(graph, path, file.read_bytes())
            # Один плохой файл не должен срывать индекс всего репозитория.
            except Exception as exc:  # noqa: BLE001
                graph.failed.append((path, f"{type(exc).__name__}: {exc}"))
        on_file()
    _link_calls(graph)
    return graph


def _link_calls(graph: Graph) -> None:
    """Связывает вызовы с узлами того же репозитория; вызовы наружу остаются без ребра."""
    linked: set[tuple[int, int]] = set()

    def link(source: int, found: int | None, line: int) -> None:
        if found is not None and found != source and (source, found) not in linked:
            linked.add((source, found))
            graph.edges.append((source, found, "calls", {"line": line}))

    for source, target, line in graph.calls:
        found = (
            graph.named.get(("function", ".".join(target))) if len(target) > 2 else None
        )
        if found is None:
            found = graph.named.get(("method", ".".join(target[:2])))
        link(source, found, line)
    for source, name, line in graph.local_calls:
        link(source, graph.named.get(("function", name)), line)


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


# .../<класс>/methods/<операция>/src/<секция>.plp, .../<класс>/criteria/<представление>/src/...
_PLP_PATH = re.compile(
    r"(?:^|/)(?P<cls>[^/]+)/(?P<group>methods|criteria)/(?P<member>[^/]+)/src/[^/]+\.plp$"
)
# Стандартные операции ЦФТ: что они делают с экземпляром своего класса.
_AUTO_OPERATIONS = {
    "NEW_AUTO": "insert",
    "EDIT_AUTO": "update",
    "DELETE_AUTO": "delete",
}


def _cft_table(class_name: str) -> str:
    return f"z#{class_name.lower()}"


def _cft_column(attribute: str) -> str:
    return f"c_{attribute.lower()}"


def _add_plp_file(graph: Graph, path: str, source: bytes) -> None:
    unit = plp.parse(source.decode("utf-8", errors="replace"))
    file_id = graph.node(
        "file",
        Path(path).name,
        path,
        path,
        attrs={"language": "plplus", "syntax_errors": unit.syntax_errors},
    )
    scope = path
    match = _PLP_PATH.search(path)
    if match:
        class_name, member = match["cls"].upper(), match["member"].upper()
        class_dir = path[: match.start("group") - 1]
        scope = f"{class_name}.{member}"
        class_key, method_key = ("class", class_name), ("method", scope)
        if class_key not in graph.named:
            graph.named[class_key] = graph.node(
                "class", class_name, class_name, class_dir, attrs={"type": "cft_class"}
            )
        if method_key not in graph.named:
            kind = "operation" if match["group"] == "methods" else "criteria"
            method_id = graph.named[method_key] = graph.node(
                "method",
                member,
                scope,
                f"{class_dir}/{match['group']}/{match['member']}",
                attrs={"type": kind},
            )
            graph.edges.append((graph.named[class_key], method_id, "contains", {}))
            if member in _AUTO_OPERATIONS and kind == "operation":
                access = _AUTO_OPERATIONS[member]
                graph.refs.append(
                    (
                        method_id,
                        "writes",
                        _cft_table(class_name),
                        None,
                        {"access": access},
                    )
                )
        method_id = graph.named[method_key]
        graph.edges.append((method_id, file_id, "contains", {}))
        if unit.own_writes and match["group"] == "methods":
            # Присваивание `[ATTR] := ...` меняет экземпляр своего класса.
            access = _AUTO_OPERATIONS.get(member, "update")
            if member not in _AUTO_OPERATIONS:
                graph.refs.append(
                    (
                        file_id,
                        "writes",
                        _cft_table(class_name),
                        None,
                        {"access": access},
                    )
                )
            for attribute in sorted(unit.own_writes):
                graph.refs.append(
                    (
                        file_id,
                        "uses",
                        _cft_table(class_name),
                        _cft_column(attribute),
                        {"roles": ["write"]},
                    )
                )

    function_ids: list[int] = []
    names: list[str] = []
    for function in unit.functions:
        parent = scope if function.parent is None else names[function.parent]
        names.append(f"{parent}.{function.name}")
        function_id = graph.node(
            "function",
            function.name,
            names[-1],
            path,
            function.start_line,
            function.end_line,
        )
        function_ids.append(function_id)
        graph.named.setdefault(("function", names[-1]), function_id)
        owner = file_id if function.parent is None else function_ids[function.parent]
        graph.edges.append((owner, function_id, "contains", {}))

    def owner_of(index: int | None) -> int:
        return file_id if index is None else function_ids[index]

    for query in unit.queries:
        query_id = graph.node(
            "sql_query",
            " ".join(query.text.split())[:120],
            f"{path}:{query.line}",
            path,
            query.line,
            query.line,
            {
                "text": query.text,
                "language": "plplus",
                "operation": query.operation,
                "partial": False,
                "parsed": True,
            },
        )
        graph.edges.append(
            (owner_of(query.owner), query_id, "executes", {"line": query.line})
        )
        for class_name, accesses in query.classes.items():
            for access in sorted(accesses):
                kind = "reads" if access == "read" else "writes"
                graph.refs.append(
                    (query_id, kind, _cft_table(class_name), None, {"access": access})
                )
        for (class_name, attribute), roles in query.attributes.items():
            graph.refs.append(
                (
                    query_id,
                    "uses",
                    _cft_table(class_name),
                    _cft_column(attribute),
                    {"roles": sorted(roles)},
                )
            )
    for call in unit.calls:
        graph.calls.append((owner_of(call.owner), call.target, call.line))
    # Имя считается вызовом, только если в этом файле или в этой операции есть такая функция.
    for (owner, name), line in unit.local_names.items():
        graph.local_calls.append((owner_of(owner), f"{scope}.{name}", line))


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
