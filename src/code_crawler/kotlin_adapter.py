"""Captured Kotlin syntax facts and conservative repository-local call resolution."""

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from importlib.metadata import version

import tree_sitter_kotlin
from tree_sitter import Language, Node, Parser

from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.java_semantic import semantic_constructions
from code_crawler.java_symbols import extract as extract_java
from code_crawler.source_adapters import (
    AdapterDescriptor,
    AdapterFileResult,
    SourceRoute,
)
from code_crawler.sql import looks_like_sql
from code_crawler.ucm import (
    CallableSignature,
    Certainty,
    CodeEntity,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    Occurrence,
    Operation,
    Position,
    Relation,
    RelationKind,
    Resolution,
    Scope,
    SourceDiagnostic,
    SourceRange,
    SqlConstruction,
    SqlExecute,
    SqlFragment,
    SqlVariant,
    Symbol,
    SymbolSelector,
    TypeRef,
    Value,
    callable_key,
    logical_id,
)

LIMITS = "syntax-only Kotlin; compiler inference, virtual dispatch, generated members and runtime flow are unsupported"


def capabilities() -> tuple[Coverage, ...]:
    """Declare bounded Kotlin v1 coverage without claiming compiler completeness."""
    return tuple(
        Coverage(
            capability=name, analyzer_version="1", status="PARTIAL", reasons=(LIMITS,)
        )
        for name in (
            "kotlin.symbols",
            "kotlin.calls",
            "kotlin.sql.construction",
            "kotlin.sql.execution",
            "sql.semantic.access",
        )
    )


def _text(node: Node) -> str:
    return node.text.decode("utf-8")


def _children(node: Node, kind: str) -> list[Node]:
    return [c for c in node.named_children if c.type == kind]


def _walk(node: Node) -> Iterator[Node]:
    yield node
    for child in node.named_children:
        yield from _walk(child)


@dataclass
class _Frame:
    scope: Scope
    parent: "_Frame | None"
    owner: Symbol | None
    bindings: dict[str, list[Symbol]] = field(default_factory=dict)


class _Extractor:
    def __init__(self, source: SourceInput):
        self.source = source
        if len(source.content) > 2_000_000:
            raise ValueError("Kotlin source exceeds 2 MB analysis limit")
        source.content.decode("utf-8")
        self.tree = Parser(Language(tree_sitter_kotlin.language())).parse(
            source.content
        )
        self.entities = {}
        self.frames = {}
        self.declarations = set()
        self.call_names = set()
        self.receivers = {}
        self.call_nodes = []
        self.ineligible = set()
        self.polymorphic = set()
        self.barriers = set()
        self.initializers = {}
        self.sql_executions = []
        self.imports = {}
        self.package = ""
        self.diagnostics = []
        for node in self.tree.root_node.named_children:
            if node.type == "package_header":
                self.package = _text(node.named_children[0])
            elif node.type == "import":
                qualified = _text(node.named_children[0])
                alias = _children(node, "identifier")
                self.imports[
                    _text(alias[-1]) if alias else qualified.rsplit(".", 1)[-1]
                ] = qualified

    def location(self, node):
        return SourceRange(
            source_file_id=self.source.file.id,
            start=Position(
                line=node.start_point.row + 1, byte_column=node.start_point.column
            ),
            end=Position(
                line=node.end_point.row + 1, byte_column=node.end_point.column
            ),
        )

    def env(self, kind, key, name, node):
        return {
            "repository_id": self.source.file.repository_id,
            "logical_key": key,
            "id": logical_id(self.source.file.repository_id, kind, key),
            "name": name,
            "source_range": self.location(node),
        }

    def key(self, tag, node):
        return f"kotlin:{self.source.file.path}:{tag}:{node.start_byte}"

    def add(self, entity):
        if entity.id in self.entities:
            raise ValueError("duplicate Kotlin declaration: " + entity.name)
        self.entities[entity.id] = entity
        return entity

    def scope(self, node, kind, parent=None, owner=None):
        scope = self.add(
            Scope(
                **self.env(
                    EntityType.SCOPE, self.key("scope:" + kind, node), kind, node
                ),
                scope_kind=kind,
                parent_scope_id=parent.scope.id if parent else None,
                owner_symbol_id=owner.id if owner else None,
            )
        )
        return _Frame(scope, parent, owner)

    def relation(self, origin, target, node, kind, capability=0):
        return self.add(
            Relation(
                **self.env(
                    EntityType.RELATION,
                    self.key(kind.value + ":" + origin.id + ":" + target.id, node),
                    kind.value,
                    node,
                ),
                relation_kind=kind,
                source=EntityRef(entity_type=origin.entity_type, id=origin.id),
                resolution=Resolution(
                    status="RESOLVED",
                    target=EntityRef(entity_type=target.entity_type, id=target.id),
                ),
                certainty=Certainty.STATIC_PROVEN,
                evidence=(
                    Evidence(
                        source_range=self.location(node),
                        analyzer="kotlin",
                        analyzer_version="1",
                        rule=kind.value,
                        description="explicit lexical syntax and exact local signature",
                    ),
                ),
                coverage=capabilities()[capability],
            )
        )

    def occurrence(self, node, frame, kind, target=None):
        occurrence = self.add(
            Occurrence(
                **self.env(
                    EntityType.OCCURRENCE, self.key(kind, node), _text(node), node
                ),
                occurrence_kind=kind,
                scope_id=frame.scope.id,
                resolution="RESOLVED" if target else "UNRESOLVED",
                target_symbol_id=target.id if target else None,
            )
        )
        if target:
            self.relation(
                occurrence,
                target,
                node,
                RelationKind.DECLARES
                if kind == "DECLARATION"
                else RelationKind.REFERENCES,
            )

    def declare(
        self,
        node,
        name_node,
        frame,
        kind,
        type_name=None,
        signature=None,
        receiver=None,
    ):
        name = _text(name_node).strip("`")
        prefix = frame.owner.qualified_name if frame.owner else self.package
        owner_key = (
            frame.owner.logical_key
            if frame.owner
            else "kotlin:file:" + self.source.file.path
        )
        if receiver:
            owner_key += ":receiver:" + receiver
        key = (
            callable_key(owner_key, name, signature)
            if signature
            else self.key(kind, name_node)
        )
        symbol = self.add(
            Symbol(
                **self.env(EntityType.SYMBOL, key, name, name_node),
                symbol_kind=kind,
                qualified_name=(prefix + "." if prefix else "") + name,
                scope_id=frame.scope.id,
                type_ref=TypeRef(name=type_name) if type_name else None,
                owner_key=owner_key if signature else None,
                signature=signature,
            )
        )
        frame.bindings.setdefault(name, []).append(symbol)
        self.declarations.add(name_node.id)
        self.occurrence(name_node, frame, "DECLARATION", symbol)
        if receiver:
            self.receivers[symbol.id] = receiver
        return symbol

    def type_name(self, node):
        return re.sub(r"\s+", "", _text(node))

    def parameters(self, node):
        container = next(
            (
                c
                for c in node.named_children
                if c.type in ("function_value_parameters", "class_parameters")
            ),
            None,
        )
        return (
            [
                c
                for c in container.named_children
                if c.type in ("parameter", "class_parameter")
            ]
            if container
            else []
        )

    def parameter_type(self, node):
        types = [
            c
            for c in node.named_children
            if c.type in ("user_type", "nullable_type", "function_type")
        ]
        return self.type_name(types[0]) if types else "kotlin.unknown"

    def collect(self, node, frame):
        kind = node.type
        if kind in ("class_declaration", "object_declaration"):
            name = node.child_by_field_name("name")
            symbol = self.declare(node, name, frame, "CLASS")
            if re.search(r"\b(interface|open|abstract)\b", _text(node).split("{")[0]):
                self.polymorphic.add(symbol.id)
            frame = self.scope(node, "TYPE", frame, symbol)
        elif kind in (
            "function_declaration",
            "secondary_constructor",
            "primary_constructor",
        ):
            name = node.child_by_field_name("name")
            constructor = kind != "function_declaration"
            if constructor:
                name = next((c for c in node.children if c.type == "constructor"), node)
            params = self.parameters(node)
            types = [
                c
                for c in node.named_children
                if c.type in ("user_type", "nullable_type", "function_type")
            ]
            receiver = next(
                (
                    self.type_name(c)
                    for c in types
                    if name and c.end_byte <= name.start_byte
                ),
                None,
            )
            returns = next(
                (
                    self.type_name(c)
                    for c in types
                    if name and c.start_byte > name.end_byte
                ),
                "kotlin.unknown",
            )
            sig = CallableSignature(
                parameter_types=tuple(
                    TypeRef(name=self.parameter_type(p)) for p in params
                ),
                return_type=TypeRef(name=returns),
            )
            # Primary constructors have no name token; use a stable synthetic callable name.
            if constructor:
                owner = frame.owner
                key = callable_key(owner.logical_key, "<init>", sig)
                symbol = self.add(
                    Symbol(
                        **self.env(EntityType.SYMBOL, key, "<init>", node),
                        symbol_kind="CONSTRUCTOR",
                        qualified_name=owner.qualified_name + ".<init>",
                        scope_id=frame.scope.id,
                        owner_key=owner.logical_key,
                        signature=sig,
                    )
                )
            else:
                symbol = self.declare(
                    node, name, frame, "METHOD", signature=sig, receiver=receiver
                )
            if frame.owner and frame.owner.id in self.polymorphic:
                self.ineligible.add(symbol.id)
            if any(
                c.type == "type_parameters" for c in node.named_children
            ) or re.search(
                r"\b(vararg|open|override|suspend|private|protected)\b",
                _text(node).split("{")[0],
            ):
                self.ineligible.add(symbol.id)
            frame = self.scope(node, "CALLABLE", frame, symbol)
        elif kind in ("block", "lambda_literal", "for_statement", "catch_block"):
            frame = self.scope(node, "BLOCK", frame, frame.owner)
            if kind != "block":
                self.barriers.add(frame.scope.id)
        self.frames[node.id] = frame
        if kind in ("parameter", "class_parameter"):
            name = next(c for c in node.named_children if c.type == "identifier")
            self.declare(node, name, frame, "PARAMETER", self.parameter_type(node))
            if (
                kind == "class_parameter"
                and re.search(r"\b(val|var)\b", _text(node))
                and frame.parent
            ):
                owner = frame.parent.owner
                property_symbol = self.add(
                    Symbol(
                        **self.env(
                            EntityType.SYMBOL,
                            self.key("constructor-property", name),
                            _text(name),
                            name,
                        ),
                        symbol_kind="FIELD",
                        qualified_name=owner.qualified_name + "." + _text(name),
                        scope_id=frame.parent.scope.id,
                        type_ref=TypeRef(name=self.parameter_type(node)),
                    )
                )
                frame.parent.bindings.setdefault(_text(name), []).append(
                    property_symbol
                )
                self.relation(owner, property_symbol, name, RelationKind.CONTAINS)
        elif kind == "property_declaration":
            variables = _children(node, "variable_declaration")
            for variable in variables:
                name = next(
                    c for c in variable.named_children if c.type == "identifier"
                )
                type_name = self.parameter_type(variable)
                initializer = (
                    node.named_children[-1]
                    if node.named_children[-1] != variable
                    else None
                )
                if type_name == "kotlin.unknown" and initializer:
                    type_name = self.literal_type(initializer) or type_name
                symbol = self.declare(
                    node,
                    name,
                    frame,
                    "LOCAL_VARIABLE"
                    if frame.owner and frame.owner.signature
                    else "FIELD",
                    type_name,
                )
                if (
                    initializer
                    and _text(node).lstrip().startswith("val ")
                    and symbol.symbol_kind == "LOCAL_VARIABLE"
                    and not any(
                        c.type in ("getter", "setter", "property_delegate")
                        for c in node.named_children
                    )
                ):
                    self.initializers[symbol.id] = initializer
        elif kind == "call_expression":
            self.call_nodes.append(node)
        for child in node.named_children:
            self.collect(child, frame)

    def lookup(self, name, node, frame):
        while frame:
            bindings = [
                s
                for s in frame.bindings.get(name, ())
                if s.symbol_kind != "LOCAL_VARIABLE"
                or (s.source_range.start.line, s.source_range.start.byte_column)
                < (node.start_point.row + 1, node.start_point.column)
            ]
            if bindings:
                return bindings[0] if len(bindings) == 1 else None
            frame = frame.parent
        return None

    def literal_type(self, node):
        if node.type == "string_literal" and not any(
            c.type == "interpolation" for c in node.named_children
        ):
            return "String"
        if node.type == "number_literal" and re.fullmatch(r"[0-9]+", _text(node)):
            return "Int"
        if _text(node) in ("true", "false"):
            return "Boolean"
        return None

    def expression_type(self, node, frame):
        if node.type == "identifier":
            symbol = self.lookup(_text(node), node, frame)
            return symbol.type_ref.name if symbol and symbol.type_ref else None
        return self.literal_type(node)

    def prepare(self):
        pending = [(self.tree.root_node, 0)]
        count = 0
        while pending:
            current, depth = pending.pop()
            count += 1
            if depth > 150 or count > 100_000:
                raise ValueError("Kotlin syntax complexity limit exceeded")
            pending.extend((c, depth + 1) for c in current.named_children)
        if self.tree.root_node.has_error:
            self.diagnostics.append(
                SourceDiagnostic(
                    severity="ERROR",
                    code="kotlin.PARSE_ERROR",
                    message="invalid or unsupported Kotlin syntax; semantic facts suppressed",
                    source_range=self.location(self.tree.root_node),
                )
            )
            return
        self.collect(self.tree.root_node, self.scope(self.tree.root_node, "FILE"))
        if self.source.file.path.endswith(".kts"):
            self.diagnostics.append(
                SourceDiagnostic(
                    severity="WARNING",
                    code="kotlin.SCRIPT_PARTIAL",
                    message="script bindings, implicit receivers and host dependencies are unresolved",
                )
            )

    def references(self):
        for node in _walk(self.tree.root_node):
            if (
                node.type != "identifier"
                or node.id in self.declarations
                or node.id in self.call_names
            ):
                continue
            parent = node.parent
            if parent is None or parent.type not in (
                "value_argument",
                "binary_expression",
                "function_body",
                "return_expression",
                "assignment",
                "property_declaration",
                "navigation_expression",
            ):
                continue
            if (
                parent.type == "navigation_expression"
                and parent.named_children[0] != node
            ):
                continue
            frame = self.frames[node.id]
            target = self.lookup(_text(node), node, frame)
            if target and not target.signature:
                write = parent.type == "assignment" and parent.named_children[0] == node
                self.occurrence(node, frame, "WRITE" if write else "READ", target)
                if write:
                    self.initializers.pop(target.id, None)

    def calls(self, catalog, receiver_types):
        for node in self.call_nodes:
            frame = self.frames[node.id]
            callee = node.named_children[0]
            args_node = next(iter(_children(node, "value_arguments")), None)
            args = (
                [a.named_children[-1] for a in args_node.named_children]
                if args_node
                else []
            )
            receiver = None
            name_node = callee
            if (
                callee.type == "navigation_expression"
                and len(callee.named_children) == 2
            ):
                receiver, name_node = callee.named_children
            self.call_names.add(name_node.id)
            name = _text(name_node).strip("`")
            types = tuple(self.expression_type(a, frame) for a in args)
            receiver_type = self.expression_type(receiver, frame) if receiver else None
            candidates = []
            # Named/default/vararg/generic/safe calls require compiler applicability.
            simple = (
                args_node is not None
                and len(node.named_children) == 2
                and all(len(a.named_children) == 1 for a in args_node.named_children)
            )
            shadow = (
                self.lookup(name, node, frame)
                if receiver is None
                else self.lookup(_text(receiver), node, frame)
            )
            blocked = shadow and (
                receiver is None
                and not shadow.signature
                or receiver is not None
                and shadow.signature
            )
            if simple and all(types) and "?." not in _text(callee) and not blocked:
                for symbol, path, language in catalog.get(name, ()):
                    if symbol.name != name or not symbol.signature:
                        continue
                    expected = tuple(t.name for t in symbol.signature.parameter_types)
                    if language == "java":
                        expected = tuple(
                            {
                                "int": "Int",
                                "java.lang.String": "String",
                                "boolean": "Boolean",
                            }.get(t, t)
                            for t in expected
                        )
                    if expected != types or any(
                        t not in {"Int", "String", "Boolean"}
                        or t in self.shadowed_builtins
                        for t in expected
                    ):
                        continue
                    extension = receiver_types.get(symbol.id)
                    visible = (
                        self.package == symbol.qualified_name.rpartition(".")[0]
                        or self.imports.get(name) == symbol.qualified_name
                    )
                    if symbol.id in self.ineligible_catalog:
                        continue
                    if receiver is not None:
                        if (
                            extension
                            and extension == receiver_type
                            and receiver_type in {"Int", "String", "Boolean"}
                            and receiver_type not in self.shadowed_builtins
                            and visible
                            or language == "java"
                            and symbol.id in self.java_static
                            and shadow is None
                            and self.imports.get(_text(receiver), _text(receiver))
                            == symbol.qualified_name.rpartition(".")[0]
                        ):
                            candidates.append(symbol)
                    elif language == "kotlin" and not extension:
                        visible = (
                            self.package == symbol.qualified_name.rpartition(".")[0]
                            or self.imports.get(name) == symbol.qualified_name
                        )
                        local = symbol.owner_key == (
                            frame.owner.owner_key
                            if frame.owner and frame.owner.signature
                            else ""
                        )
                        if visible or local:
                            candidates.append(symbol)
            target = candidates[0] if len(candidates) == 1 else None
            self.occurrence(name_node, frame, "CALL", target)
            owner = frame.owner
            if owner and owner.signature and target:
                self.relation(owner, target, node, RelationKind.CALLS, 1)
            elif not target:
                origin = owner or frame.scope
                # ExternalReference sources accept symbols/occurrences, not scopes.
                occurrence = next(
                    e
                    for e in reversed(tuple(self.entities.values()))
                    if isinstance(e, Occurrence)
                )
                if not owner:
                    origin = occurrence
                reference = self.add(
                    ExternalReference(
                        **self.env(
                            EntityType.EXTERNAL_REFERENCE,
                            self.key("external", node),
                            _text(callee),
                            node,
                        ),
                        source=EntityRef(entity_type=origin.entity_type, id=origin.id),
                        selector=SymbolSelector(qualified_name=_text(callee)),
                        reason="unknown or ambiguous receiver/argument types, dispatch or unavailable local target",
                        evidence=(
                            Evidence(
                                source_range=self.location(node),
                                analyzer="kotlin",
                                analyzer_version="1",
                                rule="deferred-call",
                                description=LIMITS,
                            ),
                        ),
                        certainty=Certainty.UNKNOWN,
                        coverage=capabilities()[1],
                    )
                )
                self.relation(
                    origin, reference, node, RelationKind.EXTERNAL_DEPENDENCY, 1
                )
            self.sql(node, frame, callee, receiver, name, args)

    def sql_value(self, node, frame, active=frozenset()):
        if node.id in active or len(active) > 30:
            return None
        active = active | {node.id}
        if node.type == "identifier":
            binding = self.lookup(_text(node), node, frame)
            initializer = self.initializers.get(binding.id) if binding else None
            return (
                self.sql_value(initializer, self.frames[initializer.id], active)
                if initializer
                else None
            )
        if node.type == "binary_expression" and any(
            c.type == "+" for c in node.children
        ):
            values = [self.sql_value(c, frame, active) for c in node.named_children]
            return "".join(values) if all(v is not None for v in values) else None
        if node.type != "string_literal":
            return None
        raw = _text(node)
        if (raw.startswith('"""') and "$" in raw) or re.search(r"(?<!\\)\$", raw):
            return None
        try:
            return raw[3:-3] if raw.startswith('"""') else json.loads(raw)
        except ValueError:
            return None

    def sql(self, node, frame, callee, receiver, name, args):
        if not args or not frame.owner or not frame.owner.signature or receiver is None:
            return
        receiver_type = self.expression_type(receiver, frame)
        qualified = self.imports.get(receiver_type, receiver_type)
        supported = {
            "java.sql.Connection": {"prepareStatement", "prepareCall"},
            "java.sql.Statement": {"execute", "executeQuery", "executeUpdate"},
            "org.springframework.jdbc.core.JdbcTemplate": {
                "query",
                "queryForObject",
                "queryForList",
                "update",
                "execute",
            },
        }
        if name not in supported.get(qualified, set()):
            return
        argument = args[0]
        value = self.sql_value(argument, frame)
        if value is None:
            self.diagnostics.append(
                SourceDiagnostic(
                    severity="WARNING",
                    code="kotlin.SQL_DYNAMIC",
                    message="SQL argument is outside immutable literal/concatenation coverage",
                    source_range=self.location(node),
                )
            )
            return
        if not looks_like_sql(value):
            return
        candidate = self.add(
            CodeEntity(
                **self.env(
                    EntityType.SQL_CANDIDATE,
                    self.key("candidate", node),
                    value,
                    argument,
                ),
                entity_type=EntityType.SQL_CANDIDATE,
            )
        )
        construction = self.add(
            SqlConstruction(
                **self.env(
                    EntityType.SQL_CONSTRUCTION,
                    self.key("construction", node),
                    value,
                    argument,
                ),
                owner_symbol_id=frame.owner.id,
                variants=(
                    SqlVariant(
                        candidate_id=candidate.id,
                        partial=False,
                        text=value,
                        fragments=(
                            SqlFragment(
                                kind="STATIC",
                                text=value,
                                source_range=self.location(argument),
                            ),
                        ),
                    ),
                ),
            )
        )
        self.relation(frame.owner, construction, node, RelationKind.CONSTRUCTS_SQL, 2)
        self.relation(construction, candidate, node, RelationKind.HAS_SQL_CANDIDATE, 2)
        # prepareStatement constructs a prepared statement; it does not execute it.
        if qualified != "java.sql.Connection":
            inputs = tuple(
                self.add(
                    Value(
                        **self.env(
                            EntityType.VALUE,
                            self.key("argument:" + str(i), node),
                            "SQL argument",
                            argument_node,
                        ),
                        value_kind="LITERAL" if i == 0 else "UNKNOWN",
                        literal=value if i == 0 else None,
                    )
                ).id
                for i, argument_node in enumerate(args)
            )
            operation = self.add(
                Operation(
                    **self.env(
                        EntityType.OPERATION,
                        self.key("operation", node),
                        _text(callee),
                        node,
                    ),
                    operation_kind="CALL",
                    input_value_ids=inputs,
                    scope_id=frame.scope.id,
                    callee=TypeRef(name=qualified + "." + name),
                )
            )
            execution = self.add(
                SqlExecute(
                    **self.env(
                        EntityType.SQL_EXECUTE, self.key("execute", node), name, node
                    ),
                    owner_symbol_id=frame.owner.id,
                    operation_id=operation.id,
                    api=qualified + "." + name,
                    sql_argument_index=0,
                )
            )
            self.sql_executions.append((execution, construction, node))
            self.relation(frame.owner, execution, node, RelationKind.EXECUTES_SQL, 3)
            self.relation(
                execution, construction, node, RelationKind.USES_SQL_CONSTRUCTION, 3
            )


@dataclass(frozen=True)
class KotlinSourceAdapter:
    """Kotlin v1; optional inventory preparation only reads captured repository bytes."""

    @property
    def descriptor(self) -> AdapterDescriptor:
        return AdapterDescriptor(
            key="kotlin",
            version="1",
            routes=(
                SourceRoute(suffix=".kt", language="kotlin"),
                SourceRoute(suffix=".kts", language="kotlin"),
            ),
            capabilities=capabilities(),
            entity_types=(
                EntityType.SYMBOL,
                EntityType.SCOPE,
                EntityType.OCCURRENCE,
                EntityType.RELATION,
                EntityType.EXTERNAL_REFERENCE,
                EntityType.SQL_CANDIDATE,
                EntityType.SQL_CONSTRUCTION,
                EntityType.OPERATION,
                EntityType.SQL_EXECUTE,
                EntityType.VALUE,
                EntityType.SQL_STATEMENT,
                EntityType.DATA_ACCESS,
            ),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> "_PreparedKotlin":
        return await self.prepare_inventory(sources, sources)

    async def prepare_inventory(
        self, sources: tuple[SourceInput, ...], inventory: tuple[SourceInput, ...]
    ) -> "_PreparedKotlin":
        """Build local signatures; Java facts retain the Java producer's canonical IDs."""
        return await asyncio.to_thread(_PreparedKotlin, sources, inventory)


class _PreparedKotlin:
    def __init__(self, sources, inventory):
        self.sources = sources
        self.inventory = inventory
        # Include negative catalog dependencies: additions/removals can change ambiguity.
        payload = [
            (s.file.path, s.file.content_sha256)
            for s in inventory
            if s.file.language in ("java", "kotlin")
        ]
        self.analysis_version = (
            "kotlin/1:tree-sitter-kotlin/"
            + version("tree-sitter-kotlin")
            + ":"
            + hashlib.sha256(json.dumps(sorted(payload)).encode()).hexdigest()
        )

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        return await asyncio.to_thread(self.analyze, sources)

    def analyze(self, sources):
        extractors = []
        catalog = []
        receivers = {}
        ineligible = set()
        static = set()
        for source in self.sources:
            try:
                extractor = _Extractor(source)
                extractor.prepare()
            except (UnicodeDecodeError, ValueError) as error:
                extractor = None
                if source in sources:
                    # Invalid bytes are reported without inventing coordinates.
                    extractors.append((source, None, str(error)))
                continue
            extractors.append((source, extractor, None))
            catalog.extend(
                (s, source.file.path, "kotlin")
                for s in extractor.entities.values()
                if isinstance(s, Symbol)
            )
            receivers.update(extractor.receivers)
            ineligible.update(extractor.ineligible)
        for source in self.inventory:
            if source.file.language != "java":
                continue
            result = extract_java(source)
            if result.diagnostics:
                continue
            symbols = [s for s in result.declared if isinstance(s, Symbol)]
            catalog.extend((s, source.file.path, "java") for s in symbols)
            # Canonical declaration nodes preserve exact overload/modifier ownership.
            for symbol in symbols:
                node = result._extractor.symbol_nodes.get(symbol.id)
                if (
                    node is not None
                    and node.type == "method_declaration"
                    and any(
                        c.type == "modifiers"
                        and {"public", "static"} <= set(_text(c).split())
                        for c in node.named_children
                    )
                ):
                    static.add(symbol.id)
        shadowed_builtins = {s.name for s, _, _ in catalog if s.symbol_kind == "CLASS"}
        by_name = defaultdict(list)
        for entry in catalog:
            by_name[entry[0].name].append(entry)
        output = []
        for source, extractor, error in extractors:
            if source not in sources:
                continue
            if extractor:
                extractor.shadowed_builtins = shadowed_builtins | {
                    name
                    for name in ("Int", "String", "Boolean")
                    if name in extractor.imports
                    and extractor.imports[name] != "kotlin." + name
                }
                extractor.java_static = static
                extractor.ineligible_catalog = ineligible
                # Record reads/writes before SQL evaluation so invalid reassignment
                # cannot leave an immutable initializer looking constant.
                extractor.call_names = {
                    n.named_children[0].id for n in extractor.call_nodes
                }
                extractor.references()
                extractor.calls(by_name, receivers)
                constructions = {
                    e.id: e
                    for e in extractor.entities.values()
                    if isinstance(e, SqlConstruction)
                }
                semantics, statements = semantic_constructions(
                    constructions,
                    source.file.repository_id,
                    "postgres",
                    capabilities()[-1],
                )
                for entity in semantics:
                    extractor.add(entity)
                for execution, construction, node in extractor.sql_executions:
                    for statement in statements[construction.id]:
                        extractor.relation(
                            execution,
                            statement,
                            node,
                            RelationKind.EXECUTES_STATEMENT,
                            4,
                        )
                for statement in (s for group in statements.values() for s in group):
                    if statement.parse_status == "ERROR":
                        extractor.diagnostics.append(
                            SourceDiagnostic(
                                severity="ERROR",
                                code="sql.CANDIDATE_PARSE_ERROR",
                                message="; ".join(statement.reasons),
                                source_range=statement.source_range,
                            )
                        )
                entities = tuple(extractor.entities.values())
                diagnostics = tuple(extractor.diagnostics)
            else:
                entities = ()
                diagnostics = (
                    SourceDiagnostic(
                        severity="ERROR", code="kotlin.EXTRACTION_ERROR", message=error
                    ),
                )
            output.append(
                AdapterFileResult(
                    analysis=FileAnalysis(
                        path=source.file.path,
                        entities=entities,
                        dependencies=tuple(
                            sorted(
                                s.file.path
                                for s in self.inventory
                                if s.file.language in ("java", "kotlin")
                                and s.file.path != source.file.path
                            )
                        ),
                    ),
                    diagnostics=diagnostics,
                )
            )
        return tuple(output)
