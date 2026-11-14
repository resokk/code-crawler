"""Local reaching Java values and execution-time JDBC/Spring binding snapshots."""

from dataclasses import dataclass

from tree_sitter import Node

from code_crawler import java
from code_crawler.java_calls import _File
from code_crawler.java_execution import (
    _PREPARED,
    JavaExecutionAnalyzer,
    _Execution,
    _ExecutionFlow,
    _Handle,
)
from code_crawler.ucm import Symbol

_SETTERS = frozenset(
    {
        "setArray",
        "setAsciiStream",
        "setBigDecimal",
        "setBinaryStream",
        "setBlob",
        "setBoolean",
        "setByte",
        "setBytes",
        "setCharacterStream",
        "setClob",
        "setDate",
        "setDouble",
        "setFloat",
        "setInt",
        "setLong",
        "setNCharacterStream",
        "setNClob",
        "setNString",
        "setNull",
        "setObject",
        "setRef",
        "setRowId",
        "setSQLXML",
        "setShort",
        "setString",
        "setTime",
        "setTimestamp",
        "setURL",
    }
)
_MAP_TYPES = {
    "java.util.Map",
    "java.util.HashMap",
    "java.util.LinkedHashMap",
    "org.springframework.jdbc.core.namedparam.MapSqlParameterSource",
}


@dataclass(frozen=True)
class CapturedValue:
    node: Node
    kind: str
    literal: str | int | float | bool | None = None
    symbol_id: str | None = None
    type_name: str | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class CapturedBinding:
    kind: str
    position: int | None
    name: str | None
    value: CapturedValue
    setter: Node | None
    api: str
    reasons: tuple[str, ...] = ()
    arguments: tuple[CapturedValue, ...] = ()


@dataclass(frozen=True)
class BindingExecution:
    execution: _Execution
    bindings: tuple[CapturedBinding, ...]
    reasons: tuple[str, ...] = ()


class BindingFlow(_ExecutionFlow):
    """Cloneable scalar value environments and local prepared binding states."""

    def __init__(
        self,
        analyzer: JavaExecutionAnalyzer,
        file: _File,
        node: Node,
        constants: dict,
        output: list[BindingExecution],
    ) -> None:
        super().__init__(analyzer, file, node, constants, [])
        self.output = output
        self.protected_maps: set[int] = set()
        self.values: dict[str, CapturedValue] = {}
        self.parameters: dict[int, dict[tuple, CapturedBinding]] = {}
        self.map_aliases: dict[str, int] = {}
        self.maps: dict[int, dict[str, CapturedValue] | None] = {}
        self.method = next(
            method
            for method in analyzer.methods.values()
            if method.node == node and method.owner.file is file
        )
        self.symbols = {
            entity.id: entity
            for entity in file.result.analysis.entities
            if isinstance(entity, Symbol)
        }
        for symbol in self.symbols.values():
            declaration = file.result._extractor.symbol_nodes[symbol.id]
            if symbol.symbol_kind != "PARAMETER" or not (
                node.start_byte < declaration.start_byte < node.end_byte
            ):
                continue
            descriptor = (
                analyzer.qualify(symbol.type_ref.name, file, self.method.owner)
                if symbol.type_ref
                else None
            )
            if descriptor in _PREPARED:
                self.handles[symbol.id] = _Handle(
                    -declaration.start_byte - 1, None, declaration, descriptor
                )

    def clone(self) -> "BindingFlow":
        result = super().clone()
        result.protected_maps = set(self.protected_maps)
        result.values = dict(self.values)
        result.parameters = {key: dict(value) for key, value in self.parameters.items()}
        result.map_aliases = dict(self.map_aliases)
        result.maps = {
            key: dict(value) if value is not None else None
            for key, value in self.maps.items()
        }
        return result

    def binding(self, node: Node | None) -> str | None:
        if node is not None:
            declaration = self.file.result._extractor.declarations.get(node.id)
            if declaration and declaration[0].symbol_kind == "PARAMETER":
                return declaration[0].id
        return super().binding(node)

    def symbol(self, node: Node) -> Symbol | None:
        if (
            node.type == "field_access"
            and java._text(node.child_by_field_name("object")) != "this"
        ):
            return None
        key = self.binding(node)
        if key:
            return self.symbols[key]
        extractor = self.file.result._extractor
        field = (
            node.child_by_field_name("field") if node.type == "field_access" else node
        )
        if field is None:
            return None
        scope = self.scopes.get(field.id)
        if scope:
            found = extractor.lookup(
                java._text(field),
                scope,
                field.start_byte,
                {"FIELD"},
                this_field=node.type == "field_access"
                and java._text(node.child_by_field_name("object")) == "this",
            )
            if len(found) == 1:
                return found[0]
        return None

    def capture(self, node: Node) -> CapturedValue:
        if node.type == "ternary_expression" and node.id in self.choices:
            return self.capture(self.choices[node.id])
        if node.type == "parenthesized_expression":
            return self.capture(node.named_children[0])
        if node.type == "unary_expression" and node.named_children:
            operand = self.capture(node.named_children[-1])
            sign = java._text(node)[:1]
            if (
                sign in ("+", "-")
                and operand.kind == "LITERAL"
                and type(operand.literal) in (int, float)
            ):
                return CapturedValue(
                    node,
                    "LITERAL",
                    operand.literal if sign == "+" else -operand.literal,
                    type_name=operand.type_name,
                )
        if node.type == "null_literal":
            return CapturedValue(node, "LITERAL")
        if java._text(node) in ("true", "false"):
            return CapturedValue(
                node, "LITERAL", java._text(node) == "true", type_name="boolean"
            )
        if node.type in (
            "decimal_integer_literal",
            "hex_integer_literal",
            "binary_integer_literal",
            "octal_integer_literal",
        ):
            text = java._text(node).replace("_", "").rstrip("lL")
            base = (
                8
                if text.startswith("0") and text.isdigit() and len(text) > 1
                else 0
                if text.lower().startswith(("0x", "0b"))
                else 10
            )
            return CapturedValue(
                node,
                "LITERAL",
                int(text, base),
                type_name="long" if java._text(node).lower().endswith("l") else "int",
            )
        if node.type in (
            "decimal_floating_point_literal",
            "hex_floating_point_literal",
        ):
            text = java._text(node).replace("_", "").rstrip("fFdD")
            number = float.fromhex(text) if "p" in text.lower() else float(text)
            if number == float("inf") or number == -float("inf"):
                return CapturedValue(
                    node, "UNKNOWN", reasons=("non-finite numeric value",)
                )
            return CapturedValue(node, "LITERAL", number, type_name="double")
        symbol = (
            self.symbol(node) if node.type in ("identifier", "field_access") else None
        )
        if symbol:
            if symbol.id in self.values:
                return self.values[symbol.id]
            if symbol.symbol_kind in ("PARAMETER", "FIELD"):
                return CapturedValue(
                    node,
                    "SYMBOLIC",
                    symbol_id=symbol.id,
                    type_name=symbol.type_ref.name if symbol.type_ref else None,
                )
            return CapturedValue(
                node, "UNKNOWN", reasons=("local value has no reaching definition",)
            )
        value = self.preview(node)
        if value is not None and value.is_string and not value.partial:
            return CapturedValue(
                node, "LITERAL", value.text, type_name="java.lang.String"
            )
        return CapturedValue(
            node, "UNKNOWN", reasons=("Java expression value is not modeled",)
        )

    def _visit(self, node: Node, depth: int) -> None:
        if node.type == "update_expression":
            for child in node.named_children:
                key = self.binding(child)
                if key:
                    self.values[key] = CapturedValue(
                        node,
                        "UNKNOWN",
                        reasons=("increment/decrement value flow is not modeled",),
                    )
        super()._visit(node, depth)

    def map_origin(self, node: Node | None) -> int | None:
        if node is None:
            return None
        if node.type == "parenthesized_expression":
            return self.map_origin(node.named_children[0])
        if (
            node.type == "method_invocation"
            and java._text(node.child_by_field_name("name")) == "addValue"
        ):
            return self.map_origin(node.child_by_field_name("object"))
        return self.map_aliases.get(self.binding(node))

    def _declare(self, declarator: Node, depth: int) -> None:
        initializer = declarator.child_by_field_name("value")
        captured = self.capture(initializer) if initializer else None
        mapping = self.read_map(initializer) if initializer else None
        alias = self.map_origin(initializer) if initializer else None
        super()._declare(declarator, depth)
        key = self.binding(declarator.child_by_field_name("name"))
        if key:
            self.values[key] = captured or CapturedValue(
                declarator, "UNKNOWN", reasons=("local value is uninitialized",)
            )
            if alias is not None:
                self.map_aliases[key] = alias
            elif mapping is not None or self.is_map_creation(initializer):
                self.map_aliases[key] = declarator.start_byte
                self.maps[declarator.start_byte] = mapping

    def _assign(self, node: Node, depth: int) -> bool:
        right = node.child_by_field_name("right")
        captured = self.capture(right)
        alias = self.map_origin(right)
        mapping = self.read_map(right)
        result = super()._assign(node, depth)
        key = self.binding(node.child_by_field_name("left"))
        if key:
            self.values[key] = (
                captured
                if java._text(node.child_by_field_name("operator")) == "="
                else CapturedValue(
                    node,
                    "UNKNOWN",
                    reasons=("compound value assignment is not modeled",),
                )
            )
            self.map_aliases.pop(key, None)
            if alias is not None:
                self.map_aliases[key] = alias
            elif mapping is not None:
                self.map_aliases[key] = node.start_byte
                self.maps[node.start_byte] = mapping
        return result

    def is_map_creation(self, node: Node | None) -> bool:
        if node is None or node.type != "object_creation_expression":
            return False
        name = java._text(node.child_by_field_name("type")).split("<", 1)[0]
        return self.analyzer.qualify(name, self.file, self.method.owner) in _MAP_TYPES

    def read_map(self, node: Node | None) -> dict[str, CapturedValue] | None:
        if node is None:
            return None
        if node.type == "parenthesized_expression":
            return self.read_map(node.named_children[0])
        origin = self.map_aliases.get(self.binding(node))
        if origin is not None:
            mapping = self.maps.get(origin)
            return dict(mapping) if mapping is not None else None
        args_node = node.child_by_field_name("arguments")
        args = tuple(args_node.named_children) if args_node else ()
        if self.is_map_creation(node):
            if not args:
                return {}
            if len(args) == 2:
                key = self.capture(args[0])
                return (
                    {key.literal: self.capture(args[1])}
                    if key.kind == "LITERAL" and isinstance(key.literal, str)
                    else None
                )
            return None
        if node.type != "method_invocation":
            return None
        name = java._text(node.child_by_field_name("name"))
        receiver = node.child_by_field_name("object")
        site = self.analyzer.sites.get(
            (self.file.source.file.path, node.child_by_field_name("name").start_byte)
        )
        descriptor, is_class = self.analyzer.receiver(site) if site else (None, False)
        if (
            is_class
            and descriptor not in self.analyzer.classes
            and (
                (descriptor == "java.util.Map" and name == "of")
                or (descriptor == "java.util.Collections" and name == "singletonMap")
            )
            and len(args) % 2 == 0
        ):
            result = {}
            for index in range(0, len(args), 2):
                key = self.capture(args[index])
                if (
                    key.kind != "LITERAL"
                    or not isinstance(key.literal, str)
                    or key.literal in result
                ):
                    return None
                result[key.literal] = self.capture(args[index + 1])
            return result
        if name == "addValue" and len(args) >= 2:
            result = self.read_map(receiver)
            key = self.capture(args[0])
            if (
                result is not None
                and key.kind == "LITERAL"
                and isinstance(key.literal, str)
            ):
                result[key.literal] = self.capture(args[1])
                return result
        return None

    def invalidate(self, handle: _Handle | None) -> None:
        if handle:
            self.parameters.pop(handle.origin, None)
        super().invalidate(handle)

    def escape(self, node: Node | None) -> None:
        pending = [node] if node else []
        while pending:
            current = pending.pop()
            origin = self.map_aliases.get(self.binding(current))
            if origin is not None and current.id not in self.protected_maps:
                self.maps[origin] = None
            pending.extend(current.named_children)
        super().escape(node)

    def _invocation(self, node: Node, depth: int) -> None:
        if node.id in self.visited:
            return
        receiver = node.child_by_field_name("object")
        name_node = node.child_by_field_name("name")
        name = java._text(name_node)
        args_node = node.child_by_field_name("arguments")
        args = tuple(args_node.named_children) if args_node else ()
        site = self.analyzer.sites.get(
            (self.file.source.file.path, name_node.start_byte)
        )
        descriptor, is_class = self.analyzer.receiver(site) if site else (None, False)
        handle = self.handle(receiver)
        if descriptor is None and handle:
            descriptor = handle.receiver_type
        if handle and descriptor in _PREPARED and not is_class:
            if name == "clearParameters" and not args:
                self.parameters[handle.origin] = {}
            elif name in _SETTERS and len(args) >= 2:
                selector = self.capture(args[0])
                value = (
                    self.capture(args[1])
                    if name != "setNull"
                    else CapturedValue(node, "LITERAL")
                )
                position = (
                    selector.literal
                    if selector.kind == "LITERAL"
                    and type(selector.literal) is int
                    and selector.literal > 0
                    else None
                )
                parameter_name = (
                    selector.literal
                    if selector.kind == "LITERAL"
                    and isinstance(selector.literal, str)
                    and descriptor == "java.sql.CallableStatement"
                    else None
                )
                kind = (
                    "POSITIONAL"
                    if position is not None
                    else "NAMED"
                    if parameter_name is not None
                    else "UNKNOWN"
                )
                state = self.parameters.setdefault(handle.origin, {})
                if kind == "UNKNOWN":
                    state.clear()
                state[(kind, position, parameter_name)] = CapturedBinding(
                    kind,
                    position,
                    parameter_name,
                    value,
                    node,
                    descriptor + "." + name,
                    ()
                    if kind != "UNKNOWN"
                    else ("JDBC selector is not a known one-based position",),
                    tuple(self.capture(arg) for arg in args),
                )
        map_origin = self.map_origin(receiver)
        if map_origin is not None and name in ("put", "addValue") and len(args) >= 2:
            mapping = self.maps.get(map_origin)
            key = self.capture(args[0])
            if (
                mapping is not None
                and key.kind == "LITERAL"
                and isinstance(key.literal, str)
            ):
                mapping[key.literal] = self.capture(args[1])
            else:
                self.maps[map_origin] = None
        if map_origin is not None:
            if name == "clear" and not args:
                self.maps[map_origin] = {}
            elif name == "remove" and len(args) == 1:
                key = self.capture(args[0])
                mapping = self.maps.get(map_origin)
                if (
                    mapping is not None
                    and key.kind == "LITERAL"
                    and isinstance(key.literal, str)
                ):
                    mapping.pop(key.literal, None)
                else:
                    self.maps[map_origin] = None
            elif name not in (
                "put",
                "addValue",
                "get",
                "containsKey",
                "containsValue",
                "size",
                "isEmpty",
                "toString",
                "hashCode",
                "equals",
            ):
                self.maps[map_origin] = None
        spring = self.spring_bindings(node, descriptor, args)
        before = len(self.events)
        protected = set(self.protected_maps)
        if descriptor and ".namedparam." in descriptor and len(args) > 1:
            self.protected_maps.add(args[1].id)
        super()._invocation(node, depth)
        self.protected_maps = protected
        for event in self.events[before:]:
            if event.site.node.id != node.id:
                continue
            h = self.handle(receiver)
            selected = tuple(self.parameters.get(h.origin, {}).values()) if h else ()
            reasons = event.reasons
            if event.reason:
                reasons = (*reasons, event.reason)
            if event.api.startswith("org.springframework."):
                selected, extra = spring
                reasons = (*reasons, *extra)
            self.output.append(
                BindingExecution(event, selected, tuple(dict.fromkeys(reasons)))
            )

    def spring_bindings(
        self, node: Node, descriptor: str | None, args: tuple[Node, ...]
    ) -> tuple[tuple[CapturedBinding, ...], tuple[str, ...]]:
        if descriptor is None or not descriptor.startswith("org.springframework."):
            return (), ()
        api = descriptor + "." + java._text(node.child_by_field_name("name"))
        if "batch" in api.lower():
            return (), ("batch binding snapshots are not modeled",)
        if ".namedparam." in descriptor:
            mapping = self.read_map(args[1]) if len(args) > 1 else None
            if mapping is None:
                return (), ("named parameter map/source is unknown",)
            return tuple(
                CapturedBinding(
                    "NAMED",
                    None,
                    key,
                    value,
                    None,
                    api,
                    ("collection parameter expansion is not modeled",)
                    if value.type_name
                    and (
                        "[]" in value.type_name
                        or any(
                            part in value.type_name
                            for part in ("List<", "Set<", "Collection<")
                        )
                    )
                    else (),
                )
                for key, value in sorted(mapping.items())
            ), ()
        name = java._text(node.child_by_field_name("name"))
        values = list(args[1:])
        if name == "execute":
            return (), ("Spring callback bindings are not modeled",) if values else ()
        if (
            name in ("queryForObject", "queryForList")
            and values
            and values[0].type == "class_literal"
        ):
            values = values[1:]
        elif name in ("query", "queryForObject"):
            return (), ("Spring callback/legacy overload bindings are not modeled",)
        if values and values[0].type == "array_creation_expression":
            initializer = values[0].child_by_field_name("value")
            if initializer is None:
                initializer = next(
                    (
                        c
                        for c in values[0].named_children
                        if c.type == "array_initializer"
                    ),
                    None,
                )
            if initializer is None or len(values) != 1:
                return (), ("Spring argument array shape is unknown",)
            values = list(initializer.named_children)
        captured = []
        for index, expression in enumerate(values, 1):
            value = self.capture(expression)
            if value.type_name and (
                "[]" in value.type_name
                or any(
                    t in value.type_name
                    for t in ("PreparedStatementSetter", "List<", "Set<", "Collection<")
                )
            ):
                return (), (
                    "callback/array/collection parameter expansion is not modeled",
                )
            captured.append(
                CapturedBinding("POSITIONAL", index, None, value, None, api)
            )
        return tuple(captured), ()
