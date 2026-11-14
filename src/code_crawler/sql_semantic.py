"""Statement-local SQL AST effects with explicit unresolved database identities."""

from dataclasses import dataclass

import sqlglot
from sqlglot import Dialect, exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.scope import Scope, traverse_scope
from sqlglot.tokens import TokenType

from code_crawler import sql
from code_crawler.ucm import SqlAccessDetail, SqlIdentifier

DIALECTS = frozenset({"postgres", "mysql", "tsql"})
_EFFECTS = {
    exp.Insert: "INSERT",
    exp.Update: "UPDATE",
    exp.Delete: "DELETE",
    exp.Merge: "MERGE",
}
_OWNERS = (exp.Select, exp.Insert, exp.Update, exp.Delete, exp.Merge)


@dataclass(frozen=True)
class StatementAnalysis:
    text: str
    text_start: int
    text_end: int
    operation: str
    parse_status: str
    reasons: tuple[str, ...]
    accesses: tuple[SqlAccessDetail, ...]


def _identifier(node: exp.Expression | None, dialect: str) -> SqlIdentifier | None:
    if isinstance(node, exp.Star):
        return SqlIdentifier(text="*", quoted=False, normalized="*")
    if not isinstance(node, exp.Identifier):
        return None
    return SqlIdentifier(
        text=node.name,
        quoted=bool(node.args.get("quoted")),
        normalized=Dialect.get_or_raise(dialect).normalize_identifier(node.copy()).name,
    )


def _key(node: exp.Expression | None, dialect: str) -> str | None:
    identifier = _identifier(node, dialect)
    return identifier.normalized if identifier else None


def _table(node: exp.Expression | None) -> exp.Table | None:
    return (
        node.this
        if isinstance(node, exp.Schema) and isinstance(node.this, exp.Table)
        else node
        if isinstance(node, exp.Table)
        else None
    )


class _Accesses:
    def __init__(self, root: exp.Expression, dialect: str) -> None:
        self.root = root
        self.dialect = dialect
        self.facts: dict[str, SqlAccessDetail] = {}
        self.reasons: list[str] = []
        self.environments: dict[int, dict[str, exp.Table | Scope]] = {}
        self.virtual: set[int] = set()
        self.physical: set[int] = set()
        normalized = root.copy()
        originals = {
            id(copy): original
            for copy, original in zip(normalized.walk(), root.walk(), strict=True)
        }
        normalize_identifiers(normalized, dialect=dialect)
        for scope in traverse_scope(normalized):
            sources = {}
            for node, source in scope.selected_sources.values():
                alias = node.args.get("alias")
                name = (
                    alias.this
                    if alias
                    else node.this
                    if isinstance(node, exp.Table)
                    else None
                )
                key = _key(name, dialect)
                if key is not None:
                    sources[key] = (
                        originals[id(source)]
                        if isinstance(source, exp.Table)
                        else source
                    )
                if isinstance(node, exp.Table):
                    target = (
                        self.virtual if isinstance(source, Scope) else self.physical
                    )
                    target.add(id(originals[id(node)]))
            self.environments[id(originals[id(scope.expression)])] = sources

    def add(
        self,
        table: exp.Table | None,
        column: exp.Expression | None,
        kind: str,
        role: str,
        *,
        status: str | None = None,
        qualifier: exp.Expression | None = None,
        reason: str | None = None,
    ) -> None:
        parts = {}
        if table is not None:
            for field, arg in (
                ("catalog_name", "catalog"),
                ("schema_name", "db"),
                ("table_name", "this"),
            ):
                parts[field] = _identifier(table.args.get(arg), self.dialect)
        bound = status or ("BOUND" if parts.get("table_name") else "UNBOUND")
        fact = SqlAccessDetail(
            object_kind="COLUMN" if column is not None else "TABLE",
            access_kind=kind,
            role=role,
            column_name=_identifier(column, self.dialect),
            qualifier=_identifier(qualifier, self.dialect),
            binding_status=bound,
            resolution="AMBIGUOUS" if bound == "AMBIGUOUS" else "UNRESOLVED",
            reason=reason
            or (
                "database schema/connection identity is not available"
                if bound == "BOUND"
                else "SQL source cannot be bound without schema or derived-output analysis"
            ),
            **parts,
        )
        self.facts[fact.model_dump_json()] = fact

    def cte_reference(self, table: exp.Table) -> bool:
        if table.db or table.catalog:
            return False
        if id(table) in self.virtual:
            return True
        if id(table) in self.physical:
            return False
        name = _key(table.this, self.dialect)
        ancestor = table.parent
        while ancestor is not None:
            with_ = ancestor.args.get("with_")
            if with_ and any(
                _key(cte.args["alias"].this, self.dialect) == name
                for cte in with_.expressions
            ):
                return True
            ancestor = ancestor.parent
        return False

    def effect(self, table: exp.Table) -> str:
        node = table.parent if isinstance(table.parent, exp.Schema) else table
        parent = node.parent
        if isinstance(parent, exp.Into):
            return "INSERT"
        if isinstance(parent, (exp.TruncateTable, exp.Drop)):
            return "DDL"
        if node.arg_key == "this" and isinstance(parent, sql._DDL):
            return "DDL"
        if node.arg_key == "this" and type(parent) in _EFFECTS:
            if self.dialect == "mysql" and isinstance(parent, exp.Update):
                aliases = {_key(table.this, self.dialect)}
                if table.args.get("alias"):
                    aliases.add(_key(table.args["alias"].this, self.dialect))
                targets = [
                    column
                    for assignment in parent.expressions
                    for column in assignment.this.find_all(exp.Column)
                ]
                if targets and all(
                    column.table
                    and _key(column.args.get("table"), self.dialect) not in aliases
                    for column in targets
                ):
                    return "READ"
            return _EFFECTS[type(parent)]
        if isinstance(parent, exp.Index) and isinstance(self.root, exp.Create):
            return "DDL"
        return "READ"

    def target(self, node: exp.Expression) -> exp.Table | None:
        current = node
        while current is not None:
            if type(current) in _EFFECTS and _table(current.this) is not None:
                return _table(current.this)
            current = current.parent
        return None

    def environment(self, owner: exp.Expression) -> dict[str, exp.Table | Scope]:
        if isinstance(owner, exp.Select):
            return self.environments.get(id(owner), {})
        result = {}
        for table in owner.find_all(exp.Table):
            if table.find_ancestor(*_OWNERS) is not owner:
                continue
            virtual = self.cte_reference(table)
            alias = table.args.get("alias")
            key = _key(alias.this if alias else table.this, self.dialect)
            if key:
                if key in result:
                    raise ValueError("ambiguous duplicate SQL source alias")
                result[key] = exp.Subquery(this=table.copy()) if virtual else table
        return result

    def bind(self, column: exp.Column) -> tuple[exp.Table | None, str]:
        qualifier = _key(column.args.get("table"), self.dialect)
        owner = column.find_ancestor(*_OWNERS)
        while owner is not None:
            sources = self.environment(owner)
            if qualifier:
                source = sources.get(qualifier)
                if (
                    source is None
                    and qualifier == "excluded"
                    and isinstance(self.root, exp.Insert)
                ):
                    source = _table(self.root.this)
            else:
                if len(sources) > 1:
                    return None, "AMBIGUOUS"
                source = next(iter(sources.values()), None)
            if isinstance(source, exp.Table):
                # Fully qualified column syntax must agree with the named table parts.
                for part in ("db", "catalog"):
                    if column.args.get(part) is not None and _key(
                        column.args[part], self.dialect
                    ) != _key(source.args.get(part), self.dialect):
                        return None, "UNBOUND"
                return source, "BOUND"
            if source is not None:
                return None, "UNBOUND"
            owner = owner.find_ancestor(*_OWNERS)
        return None, "UNBOUND"

    def write(self, column: exp.Expression) -> tuple[exp.Table | None, str] | None:
        if isinstance(column, exp.Column) and sql._is_assignment_target(column):
            target = self.target(column)
            if column.table:
                bound, _ = self.bind(column)
                target = bound
            return target, "UPDATE"
        parent = column.parent
        if (
            isinstance(parent, exp.Tuple)
            and isinstance(parent.parent, exp.EQ)
            and parent.arg_key == "this"
            and isinstance(parent.parent.parent, exp.Update)
        ):
            return self.target(column), "UPDATE"
        if (
            isinstance(parent, exp.EQ)
            and column.arg_key == "this"
            and isinstance(parent.parent, exp.OnConflict)
        ):
            return self.target(column), "UPDATE"
        if (
            isinstance(parent, exp.Tuple)
            and isinstance(parent.parent, exp.Insert)
            and parent.arg_key == "this"
        ):
            return self.target(parent.parent), "INSERT"
        return None

    def run(self) -> tuple[SqlAccessDetail, ...]:
        for table in self.root.find_all(exp.Table):
            if (
                isinstance(self.root, exp.Alter)
                and type(table.parent).__name__ == "AlterRename"
            ):
                self.add(table, None, "DDL", "rename-target")
                continue
            effect = self.effect(table)
            if effect == "READ" and self.cte_reference(table):
                continue
            if not isinstance(table.this, exp.Identifier):
                self.reasons.append("table-valued expressions are not resolved")
                continue
            self.add(table, None, effect, "target" if effect != "READ" else "source")
            if (
                effect == "DDL"
                and isinstance(self.root, exp.Create)
                and str(self.root.args.get("kind")).upper() == "TABLE"
                and isinstance(self.root.expression, exp.Query)
                and table is _table(self.root.this)
            ):
                self.add(table, None, "INSERT", "create-as-query")
            if effect == "MERGE":
                for when in self.root.find_all(exp.When):
                    action = when.args.get("then")
                    kind = _EFFECTS.get(type(action))
                    if isinstance(action, exp.Var) and action.name.upper() == "DELETE":
                        kind = "DELETE"
                    if kind:
                        self.add(table, None, kind, "merge-action")
            if (
                effect == "INSERT"
                and self.root.args.get("conflict")
                and self.root.args["conflict"].args.get("expressions")
            ):
                self.add(table, None, "UPDATE", "conflict-action")
        for insert in self.root.find_all(exp.Insert):
            schema = insert.this
            if isinstance(schema, exp.Schema):
                for name in schema.expressions:
                    if isinstance(name, exp.Identifier):
                        self.add(_table(schema), name, "INSERT", "write")
            elif isinstance(schema, exp.Table):
                self.add(
                    schema,
                    exp.Star(),
                    "INSERT",
                    "write",
                    reason="implicit insert columns require database schema",
                )
        for definition in self.root.find_all(exp.ColumnDef):
            if isinstance(definition.this, exp.Identifier) and isinstance(
                self.root, (exp.Create, exp.Alter)
            ):
                target = _table(self.root.this)
                self.add(target, definition.this, "DDL", "definition")
        for column in self.root.find_all(exp.Column):
            if (
                isinstance(self.root, exp.Alter)
                and column.find_ancestor(exp.Select) is None
            ):
                self.add(_table(self.root.this), column.this, "DDL", "alter-definition")
                continue
            written = self.write(column)
            if written:
                self.add(
                    written[0],
                    column.this,
                    written[1],
                    "write",
                    qualifier=column.args.get("table"),
                )
                if written[0] is not None:
                    self.add(written[0], None, written[1], "column-target")
                continue
            table, status = self.bind(column)
            role = "select"
            ancestor = column.parent
            while ancestor is not None and not isinstance(ancestor, _OWNERS):
                role = sql._CLAUSES.get(type(ancestor), role)
                ancestor = ancestor.parent
            owner = column.find_ancestor(exp.Select)
            if (
                not column.table
                and owner is not None
                and role in ("order", "group", "having")
            ):
                aliases = {
                    _key(output.args["alias"], self.dialect)
                    for output in owner.selects
                    if isinstance(output, exp.Alias)
                }
                if _key(column.this, self.dialect) in aliases:
                    table, status = None, "UNBOUND"
            self.add(
                table,
                column.this,
                "READ",
                role,
                status=status,
                qualifier=column.args.get("table"),
            )
            if table is not None:
                self.add(table, None, "READ", "column-source")
        for star in self.root.find_all(exp.Star):
            if isinstance(star.parent, exp.Column) or not isinstance(
                star.parent, exp.Select
            ):
                continue
            self.add(
                None,
                star,
                "READ",
                "select",
                reason="wildcard expansion requires database schema",
            )
        for join in self.root.find_all(exp.Join):
            for identifier in join.args.get("using") or ():
                self.add(
                    None,
                    identifier,
                    "READ",
                    "join",
                    status="AMBIGUOUS",
                    reason="USING column refers to both join sides; schema is unavailable",
                )
        return tuple(self.facts[k] for k in sorted(self.facts))


def analyze_statements(
    text: str, dialect: str = "postgres"
) -> tuple[StatementAnalysis, ...]:
    """Parse statements independently; preserve decoded text offsets and unknown names."""
    if dialect not in DIALECTS:
        raise ValueError("unsupported SQL dialect profile")
    try:
        tokens = Dialect.get_or_raise(dialect).tokenize(text)
    except (SqlglotError, RecursionError) as error:
        return (
            StatementAnalysis(
                text, 0, len(text), "UNKNOWN", "ERROR", (str(error),), ()
            ),
        )
    boundaries = [
        token.end + 1 for token in tokens if token.token_type == TokenType.SEMICOLON
    ]
    if not boundaries or boundaries[-1] != len(text):
        boundaries.append(len(text))
    result = []
    start = 0
    for end in boundaries:
        meaningful = any(
            token.token_type != TokenType.SEMICOLON and start <= token.start < end
            for token in tokens
        )
        chunk = text[start:end]
        offset = start + len(chunk) - len(chunk.lstrip())
        chunk = chunk.strip()
        start = end
        if not meaningful or not chunk or not chunk.strip(";"):
            continue
        try:
            root = sqlglot.parse_one(chunk, read=dialect)
            if root is None:
                continue
            operation = sql._operation(root).upper()
            supported = isinstance(root, (exp.Query, *sql._DDL, *_EFFECTS))
            if isinstance(root, (exp.Create, exp.Alter, exp.Drop)) and str(
                root.args.get("kind", "TABLE")
            ).upper() not in ("TABLE", "VIEW", "INDEX", "MATERIALIZED VIEW"):
                supported = False
            if not supported:
                status, reasons, accesses = (
                    "UNSUPPORTED",
                    ("SQL AST operation is outside the semantic profile",),
                    (),
                )
            else:
                if isinstance(root, exp.Delete) and root.args.get("tables"):
                    raise ValueError(
                        "multi-target DELETE alias resolution is unsupported"
                    )
                collector = _Accesses(root, dialect)
                accesses = collector.run()
                reasons = tuple(dict.fromkeys(collector.reasons))
                status = "PARTIAL" if reasons else "COMPLETE"
            result.append(
                StatementAnalysis(
                    chunk,
                    offset,
                    offset + len(chunk),
                    operation
                    if operation
                    in {"SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "DDL"}
                    else "UNKNOWN",
                    status,
                    reasons,
                    accesses,
                )
            )
        except (SqlglotError, RecursionError, ValueError) as error:
            result.append(
                StatementAnalysis(
                    chunk,
                    offset,
                    offset + len(chunk),
                    "UNKNOWN",
                    "ERROR",
                    (str(error) or type(error).__name__,),
                    (),
                )
            )
    return tuple(result)
