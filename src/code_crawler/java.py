"""Разбор Java: классы, методы и SQL-запросы, восстановленные из строковых выражений."""

import hashlib
import re
import textwrap
from dataclasses import dataclass, field
from typing import Literal

import tree_sitter_java
from tree_sitter import Language, Node, Parser, Tree

from code_crawler.sql import UNKNOWN, looks_like_sql
from code_crawler.ucm import Position

_LANGUAGE = Language(tree_sitter_java.language())

_TYPES = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}
_METHODS = {
    "method_declaration",
    "constructor_declaration",
    "compact_constructor_declaration",
}
_FIELDS = {"field_declaration", "constant_declaration"}
_BUILDERS = {"StringBuilder", "StringBuffer"}
_NUMBERS = {"decimal_integer_literal", "decimal_floating_point_literal"}
# Вызовы, не меняющие текст строки настолько, чтобы это влияло на разбор SQL.
_PASS_THROUGH = {
    "toString",
    "trim",
    "strip",
    "stripIndent",
    "stripLeading",
    "stripTrailing",
    "intern",
    "toLowerCase",
    "toUpperCase",
}
# Узлы, внутри которых код выполняется не всегда или не один раз.
_CONDITIONAL = {
    "if_statement",
    "for_statement",
    "enhanced_for_statement",
    "while_statement",
    "do_statement",
    "switch_expression",
    "try_statement",
    "ternary_expression",
    "lambda_expression",
}
# Родители, в которых имя переменной — это передача готового значения дальше.
_USE_SITES = {
    "argument_list",
    "return_statement",
    "array_initializer",
    "lambda_expression",
    "yield_statement",
}
# Сюда передают JPQL/HQL, а не SQL: это предмет отдельного анализа.
_JPQL_CALLS = {"createQuery", "createNamedQuery"}
_JPQL_ANNOTATIONS = {"Query", "NamedQuery"}
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "s": " ", "b": "\b", "f": "\f", "0": "\0"}
_FORMAT_SPEC = re.compile(r"%(\d+\$)?[-#+ 0,(]*\d*(\.\d+)?([a-zA-Z%])")


@dataclass
class Query:
    text: str
    # True, если часть запроса статически неизвестна или собирается по условию.
    partial: bool
    line: int
    source_span: "SourceSpan | None" = None
    fragments: tuple["_Fragment", ...] = ()
    partial_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceSpan:
    start: Position
    end: Position
    start_byte: int
    end_byte: int


@dataclass(frozen=True)
class Diagnostic:
    code: Literal["SYNTAX_ERROR", "MISSING_TOKEN", "INVALID_UTF8"]
    message: str
    node_type: str
    source_span: SourceSpan
    severity: Literal["ERROR"] = "ERROR"


@dataclass(frozen=True)
class ParseResult:
    symbols: list["Symbol"]
    diagnostics: tuple[Diagnostic, ...]
    source_sha256: str
    byte_length: int
    coverage: Literal["COMPLETE", "PARTIAL"]
    _tree: Tree | None = field(default=None, repr=False, compare=False)
    _constant_scopes: dict = field(default_factory=dict, repr=False, compare=False)


@dataclass
class Symbol:
    kind: str  # "class" или "method"
    name: str
    qualified_name: str
    start_line: int
    end_line: int
    parent: int | None  # индекс объемлющего символа в списке
    attrs: dict[str, str] = field(default_factory=dict)
    queries: list[Query] = field(default_factory=list)
    source_span: SourceSpan | None = None


@dataclass(frozen=True)
class _Fragment:
    text: str
    dynamic: bool = False
    source_span: SourceSpan | None = None


@dataclass
class _Value:
    text: str
    partial: bool = False
    fragments: tuple[_Fragment, ...] = ()
    reasons: tuple[str, ...] = ()
    is_string: bool = True
    is_integral: bool = False

    def __post_init__(self) -> None:
        if not self.fragments:
            self.fragments = (_Fragment(self.text),)
        if self.partial and not self.reasons:
            self.reasons = ("partial recovery",)


@dataclass
class _Variable:
    value: _Value | None
    depth: int
    # Значение изменилось и ещё никуда не передано.
    dirty: bool
    line: int
    source_span: SourceSpan | None = None


def parse(source: bytes) -> list[Symbol]:
    """Extract legacy symbols; use analyze for diagnostics and source provenance."""
    return analyze(source).symbols


def _span(node: Node) -> SourceSpan:
    return SourceSpan(
        Position(line=node.start_point.row + 1, byte_column=node.start_point.column),
        Position(line=node.end_point.row + 1, byte_column=node.end_point.column),
        node.start_byte,
        node.end_byte,
    )


def _position(source: bytes, offset: int) -> Position:
    prefix = source[:offset]
    return Position(
        line=prefix.count(b"\n") + 1, byte_column=len(prefix.rsplit(b"\n", 1)[-1])
    )


def analyze(source: bytes) -> ParseResult:
    """Analyze exact UTF-8 bytes, retaining AST diagnostics and declaration spans."""
    if not isinstance(source, bytes):
        raise TypeError("Java source must be immutable bytes")
    fingerprint = hashlib.sha256(source).hexdigest()
    try:
        source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        diagnostic = Diagnostic(
            "INVALID_UTF8",
            "Source is not valid UTF-8",
            "encoding",
            SourceSpan(
                _position(source, exc.start),
                _position(source, exc.end),
                exc.start,
                exc.end,
            ),
        )
        return ParseResult([], (diagnostic,), fingerprint, len(source), "PARTIAL")
    tree = Parser(_LANGUAGE).parse(source)
    root = tree.root_node
    diagnostics = []
    pending = [root]
    while pending:
        node = pending.pop()
        if node.is_error or node.is_missing:
            code = "MISSING_TOKEN" if node.is_missing else "SYNTAX_ERROR"
            message = (
                f"Missing {node.type}"
                if node.is_missing
                else "Unrecognized Java syntax"
            )
            diagnostics.append(Diagnostic(code, message, node.type, _span(node)))
        if node.has_error or node.is_error:
            pending.extend(reversed(node.children))
    diagnostics.sort(
        key=lambda d: (
            d.source_span.start_byte,
            d.source_span.end_byte,
            d.code,
            d.node_type,
        )
    )
    package = next(
        (
            _text(child.named_children[-1])
            for child in root.named_children
            if child.type == "package_declaration"
        ),
        "",
    )
    constant_scopes = _constant_scopes(root, package)
    symbols: list[Symbol] = []
    for child in root.named_children:
        if child.type in _TYPES:
            _type(child, package, None, symbols, constant_scopes)
    return ParseResult(
        symbols,
        tuple(diagnostics),
        fingerprint,
        len(source),
        "PARTIAL" if diagnostics else "COMPLETE",
        tree,
        constant_scopes,
    )


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


def _line(node: Node) -> int:
    return node.start_point.row + 1


def _constant_scopes(root: Node, package: str) -> dict[str, dict[str, "_Value | None"]]:
    types: dict[str, tuple[Node, str | None]] = {}

    def collect(node: Node, prefix: str, parent: str | None) -> None:
        name = _text(node.child_by_field_name("name"))
        if not name:
            return
        qualified = f"{prefix}.{name}" if prefix else name
        types[qualified] = (node, parent)
        for child in _members(node.child_by_field_name("body")):
            if child.type in _TYPES:
                collect(child, qualified, qualified)

    for node in root.named_children:
        if node.type in _TYPES:
            collect(node, package, None)
    aliases: dict[str, list[str]] = {}
    fields: dict[str, dict[str, Node | None]] = {}
    values: dict[tuple[str, str], _Value | None] = {}
    for qualified, (node, parent) in types.items():
        type_aliases = {
            qualified,
            qualified.removeprefix(package + ".") if package else qualified,
        }
        if parent is None:
            type_aliases.add(qualified.rsplit(".", 1)[-1])
        for alias in type_aliases:
            aliases.setdefault(alias, []).append(qualified)
        fields[qualified] = {}
        for member in _members(node.child_by_field_name("body")):
            if member.type not in _FIELDS:
                continue
            modifiers = next(
                (c for c in member.named_children if c.type == "modifiers"), None
            )
            final = node.type in (
                "interface_declaration",
                "annotation_type_declaration",
            ) or (
                modifiers is not None
                and any(c.type == "final" for c in modifiers.children)
            )
            constant_type = _text(member.child_by_field_name("type")) in {
                "String",
                "java.lang.String",
                "byte",
                "short",
                "int",
                "long",
                "float",
                "double",
                "char",
                "boolean",
            }
            final = final and constant_type
            for declaration in member.children_by_field_name("declarator"):
                name = _text(declaration.child_by_field_name("name"))
                fields[qualified][name] = (
                    declaration.child_by_field_name("value") if final else None
                )
                values[qualified, name] = None

    def scope(qualified: str) -> dict[str, _Value | None]:
        result = {
            alias + "." + name: values[owner, name]
            for alias, owners in aliases.items()
            if len(owners) == 1
            for owner in owners
            for name in fields[owner]
        }
        chain = []
        current = qualified
        while current:
            chain.append(current)
            current = types[current][1]
        for owner in reversed(chain):
            for target in types:
                if target == owner:
                    relative = owner.rsplit(".", 1)[-1]
                elif target.startswith(owner + "."):
                    relative = target[len(owner) + 1 :]
                else:
                    continue
                result.update(
                    {
                        relative + "." + name: values[target, name]
                        for name in fields[target]
                    }
                )
            result.update({name: values[owner, name] for name in fields[owner]})
        result.update(
            {"this." + name: values[qualified, name] for name in fields[qualified]}
        )
        return result

    for _ in range(len(values) + 1):
        changed = False
        for qualified in types:
            for name, initializer in fields[qualified].items():
                if initializer is None or values[qualified, name] is not None:
                    continue
                value = _Flow(scope(qualified), []).evaluate(initializer)
                if value is not None and not value.partial:
                    values[qualified, name] = value
                    changed = True
        if not changed:
            break
    for _ in range(len(values) + 1):
        changed = False
        for qualified in types:
            for name, initializer in fields[qualified].items():
                if initializer is None or values[qualified, name] is not None:
                    continue
                value = _Flow(scope(qualified), []).evaluate(initializer)
                if value is not None:
                    values[qualified, name] = value
                    changed = True
        if not changed:
            break
    return {qualified: scope(qualified) for qualified in types}


def _type(
    node: Node,
    prefix: str,
    parent: int | None,
    symbols: list[Symbol],
    constant_scopes: dict[str, dict[str, _Value | None]],
) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None or name_node.is_missing:
        return
    name = _text(name_node)
    qualified = f"{prefix}.{name}" if prefix else name
    constants = constant_scopes.get(qualified, {})
    index = len(symbols)
    symbol = Symbol(
        "class",
        name,
        qualified,
        _line(node),
        node.end_point.row + 1,
        parent,
        {"type": _TYPES[node.type]},
        source_span=_span(node),
    )
    symbols.append(symbol)
    _Flow(constants, symbol.queries).run(node.child_by_field_name("body"), members=True)
    for member in _members(node.child_by_field_name("body")):
        if member.type in _TYPES:
            _type(member, qualified, index, symbols, constant_scopes)
        elif member.type in _METHODS:
            name_node = member.child_by_field_name("name")
            if name_node is None or name_node.is_missing:
                continue
            method_name = _text(name_node)
            method = Symbol(
                "method",
                method_name,
                f"{qualified}.{method_name}",
                _line(member),
                member.end_point.row + 1,
                index,
                source_span=_span(member),
            )
            symbols.append(method)
            _Flow(constants, method.queries).run(member)


def _members(body: Node | None) -> list[Node]:
    members: list[Node] = []
    for child in body.named_children if body is not None else []:
        if child.type == "enum_body_declarations":
            members.extend(child.named_children)
        else:
            members.append(child)
    return members


class _Flow:
    """Проходит код по порядку, отслеживает значения строковых переменных
    и собирает строки, похожие на SQL."""

    def __init__(
        self, constants: dict[str, _Value | None], queries: list[Query]
    ) -> None:
        self.constants = constants
        self.queries = queries
        self.variables: dict[str, _Variable] = {}
        self.reads: set[str] = set()
        self.depth = 0

    def run(self, node: Node | None, members: bool = False) -> None:
        if node is None:
            return
        if not members:
            parameters = node.child_by_field_name("parameters")
            if parameters is not None:
                for param in parameters.named_children:
                    name_node = param.child_by_field_name("name")
                    if param.type == "spread_parameter":
                        declarator = next(
                            (
                                c
                                for c in param.named_children
                                if c.type == "variable_declarator"
                            ),
                            None,
                        )
                        name_node = (
                            declarator.child_by_field_name("name")
                            if declarator
                            else None
                        )
                    if name_node is not None:
                        self.variables[_text(name_node)] = _Variable(
                            None, 0, False, _line(name_node)
                        )
        if members:
            # В теле класса методы и вложенные типы разбираются отдельно.
            for member in _members(node):
                if member.type not in _TYPES and member.type not in _METHODS:
                    self._visit(member, 0)
        else:
            self._visit(node, 0)
        for variable in self.variables.values():
            if variable.dirty:
                self._emit(variable.value, variable.line, variable.source_span)

    def _emit(
        self, value: _Value | None, line: int, source_span: SourceSpan | None = None
    ) -> None:
        if value is None or not looks_like_sql(value.text):
            return
        text = value.text.strip()
        if all(
            " ".join(q.text.split()) != " ".join(text.split()) for q in self.queries
        ):
            self.queries.append(
                Query(
                    text,
                    value.partial,
                    line,
                    source_span,
                    _trim_fragments(value),
                    value.reasons,
                )
            )

    def _use(self, node: Node) -> bool:
        """Вычисляет выражение как готовую строку; True, если это удалось."""
        self.reads = set()
        value = self.evaluate(node)
        if value is None:
            return False
        self._emit(value, _line(node), _span(node))
        for name in self.reads:
            self.variables[name].dirty = False
        return True

    def _visit(self, node: Node, depth: int) -> None:
        self.depth = depth
        kind = node.type
        if kind in ("line_comment", "block_comment"):
            return
        if kind in ("annotation", "marker_annotation") and _is_jpql_annotation(node):
            return
        if kind in ("local_variable_declaration", *_FIELDS):
            for declarator in node.children_by_field_name("declarator"):
                self._declare(declarator, depth)
            return
        if kind == "assignment_expression" and self._assign(node, depth):
            return
        if kind == "method_invocation":
            self._invocation(node, depth)
            return
        if kind == "identifier":
            if node.parent is not None and node.parent.type in _USE_SITES:
                self._use(node)
            return
        if kind in (
            "string_literal",
            "binary_expression",
            "field_access",
            "object_creation_expression",
        ) and self._use(node):
            return
        inner = depth + 1 if kind in _CONDITIONAL else depth
        for child in node.named_children:
            self._visit(child, inner)

    def _declare(self, declarator: Node, depth: int) -> None:
        name = _text(declarator.child_by_field_name("name"))
        initializer = declarator.child_by_field_name("value")
        value = None
        if initializer is not None:
            self.reads = set()
            value = self.evaluate(initializer)
            for read in self.reads:
                self.variables[read].dirty = False
            if value is None:
                self._visit(initializer, depth)
        self.variables[name] = _Variable(
            value, depth, value is not None, _line(declarator), _span(declarator)
        )

    def _assign(self, node: Node, depth: int) -> bool:
        left = node.child_by_field_name("left")
        variable = (
            self.variables.get(_text(left)) if left.type == "identifier" else None
        )
        operator = node.child_by_field_name("operator").type
        if variable is None or operator not in ("=", "+="):
            return False
        right = node.child_by_field_name("right")
        self.reads = set()
        value = self.evaluate(right)
        reads = self.reads
        if value is None:
            self._visit(right, depth)
        if operator == "+=":
            value = _concat(variable.value, value)
        elif variable.dirty and _text(left) not in reads:
            # Прежнее значение перезаписывается, так никуда и не попав: это отдельный запрос.
            self._emit(variable.value, variable.line, variable.source_span)
        for read in reads:
            self.variables[read].dirty = False
        if value is not None and depth > variable.depth:
            value.partial = True
            value.reasons = tuple(
                dict.fromkeys((*value.reasons, "conditional assignment"))
            )
        variable.source_span = _span(node)
        variable.value, variable.dirty, variable.line = (
            value,
            value is not None,
            _line(node),
        )
        return True

    def _invocation(self, node: Node, depth: int) -> None:
        name = _text(node.child_by_field_name("name"))
        receiver = node.child_by_field_name("object")
        root = _chain_root(node)
        variable = (
            self.variables.get(_text(root))
            if root is not None and root.type == "identifier"
            else None
        )
        if variable is not None and name in ("append", "insert", "setLength"):
            if name == "append":
                self.evaluate(node)
            elif name == "setLength":
                variable.value, variable.dirty = _Value(""), False
            elif variable.value is not None:
                variable.value.partial = True
            return
        if self._use(node) or name in _JPQL_CALLS:
            return
        if receiver is not None:
            self._visit(receiver, depth)
        self._visit(node.child_by_field_name("arguments"), depth)

    def evaluate(self, node: Node) -> _Value | None:
        """Строковое значение выражения или None, если это не собираемая строка."""
        kind = node.type
        if kind == "string_literal":
            return _Value(
                _literal(node),
                fragments=(_Fragment(_literal(node), False, _span(node)),),
            )
        if kind == "character_literal":
            text = _literal(node)
            return _Value(
                text, fragments=(_Fragment(text, False, _span(node)),), is_string=False
            )
        if kind in _NUMBERS:
            if kind == "decimal_floating_point_literal":
                return None
            text = _text(node).replace("_", "").rstrip("lL")
            return _Value(
                text,
                fragments=(_Fragment(text, False, _span(node)),),
                is_string=False,
                is_integral=True,
            )
        if kind == "parenthesized_expression":
            return self.evaluate(node.named_children[0])
        if kind == "cast_expression":
            return self.evaluate(node.child_by_field_name("value"))
        if kind == "binary_expression":
            if node.child_by_field_name("operator").type != "+":
                return None
            left = self.evaluate(node.child_by_field_name("left"))
            right = self.evaluate(node.child_by_field_name("right"))
            if not (
                (left is not None and left.is_string)
                or (right is not None and right.is_string)
            ):
                return None
            return _concat(
                left,
                right,
                _span(node.child_by_field_name("left")),
                _span(node.child_by_field_name("right")),
            )
        if kind == "identifier":
            name = _text(node)
            if name in self.variables:
                self.reads.add(name)
                return self.variables[name].value
            value = self.constants.get(name)
            return (
                _Value(
                    value.text,
                    value.partial,
                    value.fragments,
                    value.reasons,
                    value.is_string,
                    value.is_integral,
                )
                if value is not None
                else None
            )
        if kind == "field_access":
            receiver = _text(node.child_by_field_name("object"))
            field_name = _text(node.child_by_field_name("field"))
            if receiver == "this":
                value = self.constants.get("this." + field_name)
            elif (
                receiver.split(".")[0] in self.variables
                or receiver.split(".")[0] in self.constants
                or receiver == "super"
            ):
                value = None
            else:
                value = self.constants.get(receiver + "." + field_name)
            return (
                _Value(
                    value.text,
                    value.partial,
                    value.fragments,
                    value.reasons,
                    value.is_string,
                    value.is_integral,
                )
                if value is not None
                else None
            )
        if kind == "object_creation_expression":
            return self._builder(node)
        if kind == "method_invocation":
            return self._call(node)
        return None

    def _builder(self, node: Node) -> _Value | None:
        if _text(node.child_by_field_name("type")) not in _BUILDERS:
            return None
        arguments = node.child_by_field_name("arguments").named_children
        if not arguments or arguments[0].type in _NUMBERS:
            return _Value("")
        return self.evaluate(arguments[0]) or _Value(UNKNOWN, partial=True)

    def _call(self, node: Node) -> _Value | None:
        name = _text(node.child_by_field_name("name"))
        receiver = node.child_by_field_name("object")
        arguments = node.child_by_field_name("arguments").named_children
        on_string = receiver is not None and _text(receiver) == "String"
        if receiver is None:
            return None
        if name in _PASS_THROUGH:
            return self.evaluate(receiver)
        if name in ("append", "concat") and len(arguments) == 1:
            target = self.evaluate(receiver)
            if target is None:
                return None
            value = _concat(
                target,
                self.evaluate(arguments[0]),
                _span(receiver),
                _span(arguments[0]),
            )
            if name == "append":
                root = _chain_root(node)
                variable = self.variables.get(_text(root)) if root is not None else None
                if variable is not None:
                    value.partial = value.partial or self.depth > variable.depth
                    if self.depth > variable.depth:
                        value.reasons = tuple(
                            dict.fromkeys((*value.reasons, "conditional append"))
                        )
                    variable.source_span = _span(node)
                    variable.value, variable.dirty = value, True
            return value
        if on_string and name == "valueOf" and len(arguments) == 1:
            value = self.evaluate(arguments[0])
            return (
                _Value(value.text, value.partial, value.fragments, value.reasons)
                if value is not None
                else None
            )
        if on_string and name == "join" and arguments:
            separator = self.evaluate(arguments[0])
            if separator is None:
                return None
            parts = [self.evaluate(argument) for argument in arguments[1:]]
            fragments = []
            reasons = list(separator.reasons)
            for index, part in enumerate(parts):
                if index:
                    fragments.extend(separator.fragments)
                fragments.extend(
                    part.fragments
                    if part is not None
                    else (_Fragment(UNKNOWN, True, _span(arguments[index + 1])),)
                )
                reasons.extend(
                    part.reasons if part is not None else ("dynamic fragment",)
                )
            return _Value(
                "".join(fragment.text for fragment in fragments),
                bool(reasons),
                tuple(fragments),
                tuple(dict.fromkeys(reasons)),
            )
        if (on_string and name == "format" and arguments) or name == "formatted":
            template = self.evaluate(arguments[0] if name == "format" else receiver)
            if template is None:
                return None
            values = arguments[1:] if name == "format" else arguments
            return _format(
                template,
                [
                    self.evaluate(value)
                    or _Value(
                        UNKNOWN,
                        True,
                        (_Fragment(UNKNOWN, True, _span(value)),),
                        ("dynamic fragment",),
                    )
                    for value in values
                ],
            )
        return None


def _chain_root(node: Node) -> Node | None:
    """Начало цепочки вызовов: `sb` для `sb.append(a).append(b)`."""
    while node.type == "method_invocation":
        receiver = node.child_by_field_name("object")
        if receiver is None:
            return None
        node = receiver
    return node


def _concat(
    left: _Value | None,
    right: _Value | None,
    left_span: SourceSpan | None = None,
    right_span: SourceSpan | None = None,
) -> _Value | None:
    if left is None and right is None:
        return None
    fragments = (
        left.fragments if left is not None else (_Fragment(UNKNOWN, True, left_span),)
    ) + (
        right.fragments
        if right is not None
        else (_Fragment(UNKNOWN, True, right_span),)
    )
    reasons = tuple(
        dict.fromkeys(
            (
                *(left.reasons if left is not None else ("dynamic fragment",)),
                *(right.reasons if right is not None else ("dynamic fragment",)),
            )
        )
    )
    partial = left is None or right is None or left.partial or right.partial
    return _Value("".join(f.text for f in fragments), partial, fragments, reasons)


def _trim_fragments(value: _Value) -> tuple[_Fragment, ...]:
    left = len(value.text) - len(value.text.lstrip())
    right = len(value.text.rstrip())
    return _slice_fragments(value, left, right)


def _slice_fragments(value: _Value, left: int, right: int) -> tuple[_Fragment, ...]:
    result = []
    offset = 0
    for fragment in value.fragments:
        start = max(0, left - offset)
        end = min(len(fragment.text), right - offset)
        if end > start:
            result.append(
                _Fragment(
                    fragment.text[start:end], fragment.dynamic, fragment.source_span
                )
            )
        offset += len(fragment.text)
    return tuple(result)


def _format(template: _Value, values: list[_Value | None]) -> _Value:
    fragments = []
    reasons = list(template.reasons)
    position = 0
    offset = 0
    for match in _FORMAT_SPEC.finditer(template.text):
        if match.start() > offset:
            fragments.extend(_slice_fragments(template, offset, match.start()))
        conversion = match.group(3)
        if conversion in ("%", "n"):
            fragments.append(_Fragment("%" if conversion == "%" else "\n"))
        else:
            index = int(match.group(1)[:-1]) - 1 if match.group(1) else position
            position += 0 if match.group(1) else 1
            value = values[index] if 0 <= index < len(values) else None
            fragments.extend(
                value.fragments if value is not None else (_Fragment(UNKNOWN, True),)
            )
            reasons.extend(
                value.reasons if value is not None else ("dynamic fragment",)
            )
            if (
                conversion == "d"
                and value is not None
                and not value.partial
                and not value.is_integral
            ):
                reasons.append("unsupported format argument type")
            if not re.fullmatch(r"%(?:\d+\$)?[sd]", match.group(0)):
                reasons.append("unsupported format conversion or flags")
        offset = match.end()
    if offset < len(template.text):
        fragments.extend(_slice_fragments(template, offset, len(template.text)))
    return _Value(
        "".join(f.text for f in fragments),
        template.partial or bool(reasons),
        tuple(fragments),
        tuple(dict.fromkeys(reasons)),
    )


def _decode_escape(text: str) -> str:
    if re.fullmatch(r"\\u+[0-9a-fA-F]{4}", text):
        return chr(int(text[-4:], 16))
    if re.fullmatch(r"\\[0-7]{1,3}", text):
        return chr(int(text[1:], 8))
    return _ESCAPES.get(text[1:], text[1:])


def _literal(node: Node) -> str:
    parts: list[str] = []
    for child in node.named_children:
        text = _text(child)
        if child.type == "escape_sequence":
            text = _decode_escape(text)
        parts.append(text)
    if node.type == "character_literal":
        inner = _text(node)[1:-1]
        parts = [_decode_escape(inner) if inner.startswith("\\") else inner]
    text = "".join(parts)
    try:
        text = text.encode("utf-16-le", errors="surrogatepass").decode("utf-16-le")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "unpaired Java surrogate cannot be represented in UTF-8 SQL"
        ) from exc
    # Текстовый блок: общий отступ строк в значение не входит.
    return textwrap.dedent(text) if _text(node).startswith('"""') else text


def _is_jpql_annotation(node: Node) -> bool:
    name = _text(node.child_by_field_name("name")).rsplit(".", 1)[-1]
    if name not in _JPQL_ANNOTATIONS:
        return False
    arguments = node.child_by_field_name("arguments")
    if name == "Query" and arguments is not None:
        for argument in arguments.named_children:
            if (
                argument.type == "element_value_pair"
                and _text(argument.child_by_field_name("key")) == "nativeQuery"
            ):
                value = argument.child_by_field_name("value")
                return value is None or value.type != "true"
    return True
