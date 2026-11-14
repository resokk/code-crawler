"""AST-positioned SQL placeholders and conservative column associations."""

from dataclasses import dataclass

from sqlglot import Dialect, exp

from code_crawler import sql
from code_crawler.sql_semantic import DIALECTS, _Accesses, _identifier, _table
from code_crawler.ucm import SqlAccessDetail


@dataclass(frozen=True)
class ParameterAnalysis:
    parameter_kind: str
    position: int | None
    parameter_name: str | None
    token_text: str
    text_start: int
    text_end: int
    columns: tuple[SqlAccessDetail, ...]
    reason: str | None = None


def analyze_parameters(
    text: str, dialect: str = "postgres", positional_start: int = 0
) -> tuple[ParameterAnalysis, ...]:
    """Locate true AST parameters, excluding strings/comments and JSON operators."""
    if dialect not in DIALECTS or positional_start < 0:
        raise ValueError("invalid SQL parameter profile/start")
    dialect_instance = Dialect.get_or_raise(dialect)

    class PositionedParser(dialect_instance.parser_class):
        def _parse_placeholder(self):
            token = self._curr
            result = super()._parse_placeholder()
            if isinstance(result, exp.Placeholder) and token is not None:
                result.meta.update(
                    parameter_start=token.start, parameter_end=self._prev.end + 1
                )
            return result

        def _parse_parameter(self):
            start = self._prev.start
            result = super()._parse_parameter()
            result.meta.update(parameter_start=start, parameter_end=self._prev.end + 1)
            return result

    roots = PositionedParser(dialect=dialect_instance).parse(
        dialect_instance.tokenize(text), sql=text
    )
    if len(roots) != 1 or roots[0] is None:
        raise ValueError("parameter analysis requires one parsed statement")
    root = roots[0]
    collector = _Accesses(root, dialect)
    facts = collector.run()
    result = []
    position = positional_start
    parameters = sorted(
        root.find_all(exp.Placeholder, exp.Parameter),
        key=lambda node: node.meta.get("parameter_start", -1),
    )
    comparisons = (
        exp.EQ,
        exp.NEQ,
        exp.LT,
        exp.LTE,
        exp.GT,
        exp.GTE,
        exp.In,
        exp.Between,
        exp.Like,
        exp.ILike,
        exp.Is,
    )
    for parameter in parameters:
        start, end = (
            parameter.meta.get("parameter_start"),
            parameter.meta.get("parameter_end"),
        )
        if start is None or end is None:
            raise ValueError("SQL parser did not preserve parameter position")
        token = text[start:end]
        if isinstance(parameter, exp.Placeholder) and parameter.args.get("jdbc"):
            position += 1
            kind, selected_position, name = "POSITIONAL", position, None
        elif token.startswith("$") and token[1:].isdigit() and int(token[1:]) > 0:
            kind, selected_position, name = "INDEXED", int(token[1:]), None
        else:
            kind, selected_position, name = "NAMED", None, parameter.name
        selected = []
        ancestor = parameter.parent
        while ancestor is not None and not isinstance(
            ancestor, (exp.Select, exp.Values)
        ):
            if isinstance(ancestor, comparisons):
                for column in ancestor.find_all(exp.Column):
                    if column.find_ancestor(exp.Select) is not parameter.find_ancestor(
                        exp.Select
                    ):
                        continue
                    written = collector.write(column)
                    table, access_kind = (
                        written if written else (collector.bind(column)[0], "READ")
                    )
                    selected.extend(
                        _match(
                            facts,
                            table,
                            column.this,
                            access_kind,
                            dialect,
                            column.args.get("table"),
                        )
                    )
                break
            ancestor = ancestor.parent
        if not selected:
            values = parameter.find_ancestor(exp.Values)
            insert = values.find_ancestor(exp.Insert) if values else None
            schema = insert.this if insert else None
            row = parameter
            while row.parent is not None and row.parent is not values:
                row = row.parent
            if values and isinstance(schema, exp.Schema) and isinstance(row, exp.Tuple):
                expression = parameter
                while expression.parent is not row:
                    expression = expression.parent
                index = next(
                    i for i, child in enumerate(row.expressions) if child is expression
                )
                if index < len(schema.expressions):
                    selected.extend(
                        _match(
                            facts,
                            _table(schema),
                            schema.expressions[index],
                            "INSERT",
                            dialect,
                            None,
                        )
                    )
        unique = {detail.model_dump_json(): detail for detail in selected}
        columns = tuple(unique[key] for key in sorted(unique))
        result.append(
            ParameterAnalysis(
                kind,
                selected_position,
                name,
                token,
                start,
                end,
                columns,
                None
                if columns
                else "no unambiguous comparison/assignment/INSERT column association",
            )
        )
    return tuple(result)


def _match(
    facts: tuple[SqlAccessDetail, ...],
    table: exp.Table | None,
    column: exp.Expression,
    kind: str,
    dialect: str,
    qualifier: exp.Expression | None,
) -> list[SqlAccessDetail]:
    role = "write" if kind in ("UPDATE", "INSERT") else "select"
    ancestor = column.parent
    while ancestor is not None and not isinstance(
        ancestor, (exp.Select, exp.Insert, exp.Update, exp.Delete, exp.Merge)
    ):
        role = sql._CLAUSES.get(type(ancestor), role)
        ancestor = ancestor.parent
    parts = {
        field: _identifier(table.args.get(arg), dialect) if table else None
        for field, arg in (
            ("catalog_name", "catalog"),
            ("schema_name", "db"),
            ("table_name", "this"),
        )
    }
    return [
        fact
        for fact in facts
        if fact.object_kind == "COLUMN"
        and fact.role == role
        and fact.access_kind == kind
        and fact.column_name == _identifier(column, dialect)
        and all(getattr(fact, field) == value for field, value in parts.items())
        and (qualifier is None or fact.qualifier == _identifier(qualifier, dialect))
    ]
