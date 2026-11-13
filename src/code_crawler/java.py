"""Разбор Java: классы, методы и SQL-запросы, восстановленные из строковых выражений."""

import re
import textwrap
from dataclasses import dataclass, field

import tree_sitter_java
from tree_sitter import Language, Node, Parser

from code_crawler.sql import UNKNOWN, looks_like_sql

_PARSER = Parser(Language(tree_sitter_java.language()))

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


@dataclass
class _Value:
    text: str
    partial: bool = False


@dataclass
class _Variable:
    value: _Value | None
    depth: int
    # Значение изменилось и ещё никуда не передано.
    dirty: bool
    line: int


def parse(source: bytes) -> list[Symbol]:
    root = _PARSER.parse(source).root_node
    package = next(
        (
            _text(child.named_children[-1])
            for child in root.named_children
            if child.type == "package_declaration"
        ),
        "",
    )
    constants: dict[str, _Value | None] = {}
    _collect_constants(root, constants)
    symbols: list[Symbol] = []
    for child in root.named_children:
        if child.type in _TYPES:
            _type(child, package, None, symbols, constants)
    return symbols


def _text(node: Node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _line(node: Node) -> int:
    return node.start_point.row + 1


def _collect_constants(node: Node, constants: dict[str, _Value | None]) -> None:
    # shortcut: константы видны только в пределах файла и различаются лишь по имени поля;
    # для констант из других классов нужен проход по всему репозиторию.
    if node.type in _FIELDS:
        flow = _Flow(constants, [])
        for declarator in node.children_by_field_name("declarator"):
            value = declarator.child_by_field_name("value")
            if value is not None:
                name = _text(declarator.child_by_field_name("name"))
                constants[name] = flow.evaluate(value)
        return
    for child in node.named_children:
        _collect_constants(child, constants)


def _type(
    node: Node,
    prefix: str,
    parent: int | None,
    symbols: list[Symbol],
    constants: dict[str, _Value | None],
) -> None:
    name = _text(node.child_by_field_name("name"))
    qualified = f"{prefix}.{name}" if prefix else name
    index = len(symbols)
    symbol = Symbol(
        "class",
        name,
        qualified,
        _line(node),
        node.end_point.row + 1,
        parent,
        {"type": _TYPES[node.type]},
    )
    symbols.append(symbol)
    _Flow(constants, symbol.queries).run(node.child_by_field_name("body"), members=True)
    for member in _members(node.child_by_field_name("body")):
        if member.type in _TYPES:
            _type(member, qualified, index, symbols, constants)
        elif member.type in _METHODS:
            method_name = _text(member.child_by_field_name("name"))
            method = Symbol(
                "method",
                method_name,
                f"{qualified}.{method_name}",
                _line(member),
                member.end_point.row + 1,
                index,
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
        if members:
            # В теле класса методы и вложенные типы разбираются отдельно.
            for member in _members(node):
                if member.type not in _TYPES and member.type not in _METHODS:
                    self._visit(member, 0)
        else:
            self._visit(node, 0)
        for variable in self.variables.values():
            if variable.dirty:
                self._emit(variable.value, variable.line)

    def _emit(self, value: _Value | None, line: int) -> None:
        if value is None or not looks_like_sql(value.text):
            return
        text = value.text.strip()
        if all(
            " ".join(q.text.split()) != " ".join(text.split()) for q in self.queries
        ):
            self.queries.append(Query(text, value.partial, line))

    def _use(self, node: Node) -> bool:
        """Вычисляет выражение как готовую строку; True, если это удалось."""
        self.reads = set()
        value = self.evaluate(node)
        if value is None:
            return False
        self._emit(value, _line(node))
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
            value, depth, value is not None, _line(declarator)
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
            self._emit(variable.value, variable.line)
        for read in reads:
            self.variables[read].dirty = False
        if value is not None and depth > variable.depth:
            value.partial = True
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
            return _Value(_literal(node))
        if kind == "character_literal":
            return _Value(_text(node)[1:-1])
        if kind in _NUMBERS:
            return _Value(_text(node))
        if kind == "parenthesized_expression":
            return self.evaluate(node.named_children[0])
        if kind == "cast_expression":
            return self.evaluate(node.child_by_field_name("value"))
        if kind == "binary_expression":
            if node.child_by_field_name("operator").type != "+":
                return None
            return _concat(
                self.evaluate(node.child_by_field_name("left")),
                self.evaluate(node.child_by_field_name("right")),
            )
        if kind == "identifier":
            name = _text(node)
            if name in self.variables:
                self.reads.add(name)
                return self.variables[name].value
            return self.constants.get(name)
        if kind == "field_access":
            return self.constants.get(_text(node.child_by_field_name("field")))
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
            value = _concat(target, self.evaluate(arguments[0]))
            if name == "append":
                root = _chain_root(node)
                variable = self.variables.get(_text(root)) if root is not None else None
                if variable is not None:
                    value.partial = value.partial or self.depth > variable.depth
                    variable.value, variable.dirty = value, True
            return value
        if on_string and name == "valueOf" and len(arguments) == 1:
            return self.evaluate(arguments[0])
        if on_string and name == "join" and arguments:
            separator = self.evaluate(arguments[0])
            if separator is None:
                return None
            parts = [self.evaluate(argument) for argument in arguments[1:]]
            return _Value(
                separator.text.join(part.text if part else UNKNOWN for part in parts),
                separator.partial
                or any(part is None or part.partial for part in parts),
            )
        if (on_string and name == "format" and arguments) or name == "formatted":
            template = self.evaluate(arguments[0] if name == "format" else receiver)
            if template is None:
                return None
            values = arguments[1:] if name == "format" else arguments
            return _format(template, [self.evaluate(value) for value in values])
        return None


def _chain_root(node: Node) -> Node | None:
    """Начало цепочки вызовов: `sb` для `sb.append(a).append(b)`."""
    while node.type == "method_invocation":
        receiver = node.child_by_field_name("object")
        if receiver is None:
            return None
        node = receiver
    return node


def _concat(left: _Value | None, right: _Value | None) -> _Value | None:
    if left is None and right is None:
        return None
    return _Value(
        (left.text if left else UNKNOWN) + (right.text if right else UNKNOWN),
        left is None or right is None or left.partial or right.partial,
    )


def _format(template: _Value, values: list[_Value | None]) -> _Value:
    partial = template.partial
    position = 0

    def substitute(match: re.Match[str]) -> str:
        nonlocal partial, position
        conversion = match.group(3)
        if conversion == "%":
            return "%"
        if conversion == "n":
            return "\n"
        index = int(match.group(1)[:-1]) - 1 if match.group(1) else position
        position += 0 if match.group(1) else 1
        value = values[index] if 0 <= index < len(values) else None
        partial = partial or value is None or value.partial
        return value.text if value else UNKNOWN

    return _Value(_FORMAT_SPEC.sub(substitute, template.text), partial)


def _literal(node: Node) -> str:
    parts: list[str] = []
    for child in node.named_children:
        text = _text(child)
        if child.type == "escape_sequence":
            text = _ESCAPES.get(text[1:], text[1:])
        parts.append(text)
    text = "".join(parts)
    # Текстовый блок: общий отступ строк в значение не входит.
    return textwrap.dedent(text) if _text(node).startswith('"""') else text


def _is_jpql_annotation(node: Node) -> bool:
    name = _text(node.child_by_field_name("name")).rsplit(".", 1)[-1]
    return name in _JPQL_ANNOTATIONS and not re.search(
        r"nativeQuery\s*=\s*true", _text(node)
    )
