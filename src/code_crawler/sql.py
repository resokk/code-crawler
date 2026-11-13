"""Разбор SQL (диалект PostgreSQL): таблицы, колонки, условия, соединения, происхождение колонок."""

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

# Заполнитель для фрагмента запроса, значение которого статически неизвестно.
UNKNOWN = "__unknown__"

_STATEMENTS = (exp.Select, exp.Insert, exp.Update, exp.Delete, exp.Merge)
_DML = {
    exp.Insert: "insert",
    exp.Update: "update",
    exp.Delete: "delete",
    exp.Merge: "merge",
}
_DDL = (exp.Create, exp.Alter, exp.Drop, exp.TruncateTable)
_CLAUSES = {
    exp.Where: "where",
    exp.Having: "having",
    exp.Join: "join",
    exp.Group: "group",
    exp.Order: "order",
}

_LOOKS_LIKE_SQL = re.compile(
    r"""\s*\(?\s*(
        select\b.+\bfrom\b | select\s+\w+\s*\(
      | insert\s+into\b
      | update\s+\S+\s+set\b
      | delete\s+from\b
      | with\s+(recursive\s+)?\w+.*\bas\s*\(
      | merge\s+into\b
      | (create|alter|drop)\s+(table|index|unique|view|materialized|sequence|schema|or\s+replace|temp|temporary)\b
      | truncate\s+(table\s+)?[\w.]+\s*;?\s*$
    )""",
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)


def looks_like_sql(text: str) -> bool:
    return _LOOKS_LIKE_SQL.match(text) is not None


@dataclass
class Analysis:
    parsed: bool = False
    operation: str | None = None
    # таблица -> способы доступа ("read", "insert", "update", "delete", "merge", "ddl")
    tables: dict[str, set[str]] = field(default_factory=dict)
    # (таблица, колонка) -> роли ("select", "where", "join", "group", "order", "having", "write")
    columns: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    # колонки, таблицу которых без схемы БД определить нельзя
    unresolved_columns: set[str] = field(default_factory=set)
    conditions: list[str] = field(default_factory=list)
    joins: list[dict[str, str]] = field(default_factory=list)
    # колонка результата -> исходные "таблица.колонка"
    lineage: dict[str, list[str]] = field(default_factory=dict)


def analyze(text: str) -> Analysis:
    result = Analysis()
    try:
        # JPA-параметры вида ?1 парсер не понимает; для анализа они равны обычному ?.
        statements = sqlglot.parse(re.sub(r"\?\d+", "?", text), read="postgres")
    except (sqlglot.errors.SqlglotError, RecursionError):
        return result
    statements = [s for s in statements if s is not None]
    if not statements:
        return result
    result.parsed = True
    result.operation = _operation(statements[0])
    for statement in statements:
        _Statement(statement, result).run()
    return result


def _operation(statement: exp.Expression) -> str:
    if isinstance(statement, exp.Query):
        return "select"
    if isinstance(statement, _DDL):
        return "ddl"
    return _DML.get(type(statement), type(statement).__name__.lower())


def _table_name(table: exp.Table) -> str:
    return ".".join(part.name.lower() for part in table.parts)


def _selects(query: exp.Expression | None) -> list[exp.Select]:
    """SELECT-ы верхнего уровня запроса: сам запрос либо ветки UNION / INTERSECT / EXCEPT."""
    if isinstance(query, exp.Select):
        return [query]
    if isinstance(query, exp.SetOperation):
        return _selects(query.left) + _selects(query.right)
    if isinstance(query, exp.Subquery):
        return _selects(query.this)
    return []


def _is_assignment_target(column: exp.Column) -> bool:
    """Левая часть `SET колонка = ...` в UPDATE: она всегда принадлежит изменяемой таблице."""
    parent = column.parent
    return (
        isinstance(parent, exp.EQ)
        and column.arg_key == "this"
        and isinstance(parent.parent, exp.Update)
        and parent.arg_key == "expressions"
    )


class _Statement:
    def __init__(self, root: exp.Expression, result: Analysis) -> None:
        self.root = root
        self.result = result
        self.ctes = {cte.alias.lower(): cte.this for cte in root.find_all(exp.CTE)}
        # оператор -> {псевдоним: имя таблицы | подзапрос}
        self.sources: dict[int, dict[str, str | exp.Expression]] = {}

    def run(self) -> None:
        for table in self.root.find_all(exp.Table):
            self._table(table)
        for subquery in self.root.find_all(exp.Subquery):
            if subquery.alias:
                self._add_source(subquery, subquery.alias, subquery.this)
        for column in self.root.find_all(exp.Column):
            self._column(column)
        self._written_columns()
        for clause in self.root.find_all(exp.Where, exp.Having):
            self.result.conditions.append(clause.this.sql())
        for join in self.root.find_all(exp.Join):
            self._join(join)
        self._lineage()

    def _add_source(
        self, node: exp.Expression, alias: str, source: str | exp.Expression
    ) -> None:
        owner = node.find_ancestor(*_STATEMENTS)
        if owner is not None:
            self.sources.setdefault(id(owner), {})[alias.lower()] = source

    def _table(self, table: exp.Table) -> None:
        name = _table_name(table)
        if not name or UNKNOWN in name:
            return
        if not table.db and name in self.ctes:
            self._add_source(table, table.alias_or_name, self.ctes[name])
            return
        self._add_source(table, table.alias_or_name, name)
        self.result.tables.setdefault(name, set()).add(self._access(table))

    def _access(self, table: exp.Table) -> str:
        node: exp.Expression = table
        if isinstance(node.parent, exp.Schema):
            node = node.parent
        parent = node.parent
        if isinstance(parent, exp.TruncateTable):
            return "ddl"
        if node.arg_key == "this" and isinstance(parent, _DDL):
            return "ddl"
        if node.arg_key == "this" and type(parent) in _DML:
            return _DML[type(parent)]
        return "read"

    def _resolve(self, column: exp.Column, depth: int = 0) -> set[tuple[str, str]]:
        """Базовые (таблица, колонка), из которых получена колонка; пусто — если неизвестно."""
        name = "*" if column.is_star else column.name.lower()
        qualifier = column.table.lower()
        owner = column.find_ancestor(*_STATEMENTS)
        while owner is not None:
            sources = self.sources.get(id(owner), {})
            if qualifier:
                source = sources.get(qualifier)
            else:
                # Без схемы БД колонку без префикса можно отнести к таблице,
                # только если источник у оператора один.
                source = next(iter(sources.values())) if len(sources) == 1 else None
                if source is None and sources:
                    return set()
            if isinstance(source, str):
                return {(source, name)}
            if source is not None:
                return self._through(source, name, depth)
            owner = owner.find_ancestor(*_STATEMENTS)
        return set()

    def _through(
        self, query: exp.Expression, name: str, depth: int
    ) -> set[tuple[str, str]]:
        if depth > 20:
            return set()
        found: set[tuple[str, str]] = set()
        for select in _selects(query):
            for output in select.selects:
                if (
                    name == "*"
                    or output.alias_or_name.lower() == name
                    or output.is_star
                ):
                    for column in output.find_all(exp.Column):
                        found |= self._resolve(column, depth + 1)
        return found

    def _column(self, column: exp.Column) -> None:
        if UNKNOWN in column.name:
            return
        if _is_assignment_target(column):
            return
        role = "select"
        ancestor = column.parent
        while ancestor is not None and not isinstance(ancestor, _STATEMENTS):
            if type(ancestor) in _CLAUSES:
                role = _CLAUSES[type(ancestor)]
                break
            ancestor = ancestor.parent
        resolved = self._resolve(column)
        if not resolved:
            self.result.unresolved_columns.add(column.sql().lower())
        for key in resolved:
            self.result.columns.setdefault(key, set()).add(role)

    def _written_columns(self) -> None:
        for insert in self.root.find_all(exp.Insert):
            schema = insert.this
            if isinstance(schema, exp.Schema) and isinstance(schema.this, exp.Table):
                table = _table_name(schema.this)
                for identifier in schema.expressions:
                    key = (table, identifier.name.lower())
                    self.result.columns.setdefault(key, set()).add("write")
        for column in self.root.find_all(exp.Column):
            if not _is_assignment_target(column):
                continue
            # У UPDATE внутри MERGE своей таблицы нет — изменяется цель MERGE.
            target = column.parent.parent.this or column.find_ancestor(exp.Merge).this
            if isinstance(target, exp.Table):
                key = (_table_name(target), column.name.lower())
                self.result.columns.setdefault(key, set()).add("write")

    def _join(self, join: exp.Join) -> None:
        target = join.this
        on = join.args.get("on")
        using = join.args.get("using")
        self.result.joins.append(
            {
                "type": " ".join(
                    part.lower() for part in (join.method, join.side, join.kind) if part
                )
                or "inner",
                "table": _table_name(target)
                if isinstance(target, exp.Table)
                else target.alias_or_name.lower(),
                "on": on.sql()
                if on is not None
                else ", ".join(u.name.lower() for u in using or []),
            }
        )

    def _lineage(self) -> None:
        query = self.root
        targets: list[str] = []
        if isinstance(query, exp.Insert):
            if isinstance(query.this, exp.Schema):
                targets = [i.name.lower() for i in query.this.expressions]
            query = query.expression
        selects = _selects(query)
        if not selects:
            return
        # У UNION имена колонок результата задаёт первая ветка.
        query = selects[0]
        for position, output in enumerate(query.selects):
            if position < len(targets):
                name = targets[position]
            elif output.alias or isinstance(output, exp.Column | exp.Star):
                name = output.alias_or_name
            else:
                name = output.sql()
            origins: set[tuple[str, str]] = set()
            for column in output.find_all(exp.Column):
                origins |= self._resolve(column)
            if output.is_star and not origins:
                origins = {
                    (source, "*")
                    for source in self.sources.get(id(query), {}).values()
                    if isinstance(source, str)
                }
            self.result.lineage[name.lower() or f"#{position + 1}"] = sorted(
                f"{table}.{column}" for table, column in origins
            )
