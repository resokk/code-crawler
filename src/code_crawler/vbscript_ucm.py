"""File-local VBScript facts and conservative ADODB SQL recovery from ANTLR trees."""

from dataclasses import dataclass, field

from antlr4 import ParserRuleContext

from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.java_semantic import semantic_constructions
from code_crawler.source_adapters import AdapterError, AdapterFileResult, AdapterIssue
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
    Relation,
    RelationKind,
    Resolution,
    Scope,
    SourceDiagnostic,
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
from code_crawler.vbscript_parse import VbscriptParseResult, parse_vbscript

LIMITS = "bounded VBScript syntax/local flow; Variant, ByRef, dynamic code, COM runtime binding and host composition are not resolved"
_DYNAMIC = {"eval", "execute", "executeglobal", "getref"}
_ADO = {
    name.casefold(): name
    for name in ("ADODB.Connection", "ADODB.Command", "ADODB.Recordset")
}


def capabilities() -> tuple[Coverage, ...]:
    return tuple(
        Coverage(
            capability=name,
            analyzer_version="1",
            status="COMPLETE" if i == 0 else "PARTIAL",
            reasons=() if i == 0 else (LIMITS,),
        )
        for i, name in enumerate(
            (
                "vbscript.parser.diagnostics",
                "vbscript.symbols",
                "vbscript.calls",
                "vbscript.sql.construction",
                "sql.semantic.access",
                "vbscript.sql.execution",
            )
        )
    )


def _children(node):
    return [
        c
        for c in (getattr(node, "children", None) or ())
        if isinstance(c, ParserRuleContext)
    ]


def _kind(node):
    return type(node).__name__.removesuffix("Context")


def _ref(entity):
    return EntityRef(id=entity.id, entity_type=entity.entity_type)


@dataclass
class _Frame:
    scope: Scope
    owner: Symbol
    parent: "_Frame | None"
    bindings: dict[str, Symbol] = field(default_factory=dict)
    top: bool = False
    result_name: str | None = None

    def lookup(self, name):
        frame = self
        while frame:
            if name in frame.bindings:
                return frame.bindings[name]
            frame = frame.parent
        return None


@dataclass(frozen=True)
class _Value:
    fragments: tuple[SqlFragment, ...] = ()
    literal: str | int | bool | None = None
    known: bool = False
    object_type: str | None = None
    object_id: str | None = None
    reasons: tuple[str, ...] = ()

    @property
    def text(self):
        return "".join(f.text for f in self.fragments)


class _Extract:
    def __init__(
        self, source: SourceInput, parsed: VbscriptParseResult, dialect: str
    ) -> None:
        self.source, self.mapping, self.tree = source, parsed.mapping, parsed.tree
        self.dialect = dialect
        self.entities, self.frames, self.types = {}, {}, {}
        self.bodies, self.constructions, self.executions = [], {}, []
        self.constants, self.diagnostics = {}, []
        self.caps = capabilities()
        self.epoch = 0
        self.dynamic = False
        self.explicit = False
        pending = [self.tree]
        while pending:
            node = pending.pop()
            if _kind(node) == "SimpleStatement" and node.OPTION():
                self.explicit = True
            if (
                _kind(node) == "SimpleStatement"
                and node.target()
                and node.target().identifier().getText().casefold() in _DYNAMIC
                and not node.target().suffix()
                and not node.target().getText().startswith(".")
            ):
                self.dynamic = True
            if (
                _kind(node) == "UnaryExpression"
                and node.atom().identifier()
                and node.atom().identifier().getText().casefold() in _DYNAMIC
                and node.suffix()
            ):
                self.dynamic = True
            pending.extend(_children(node))

    def location(self, node):
        return (
            self.mapping.span(*node)
            if isinstance(node, tuple)
            else self.mapping.range(node)
        )

    def key(self, tag, node):
        offset = node[0] if isinstance(node, tuple) else node.start.start
        return f"{self.source.file.path}:{tag}:{offset}"

    def env(self, etype, key, name, node):
        return {
            "repository_id": self.source.file.repository_id,
            "logical_key": key,
            "id": logical_id(self.source.file.repository_id, etype, key),
            "name": name,
            "source_range": self.location(node),
        }

    def fail(self, message, node, code="DECLARATION_ERROR"):
        raise AdapterError(
            "vbscript",
            "analyze",
            (
                AdapterIssue(
                    self.source.file.path,
                    SourceDiagnostic(
                        severity="ERROR",
                        code="vbscript." + code,
                        message=message,
                        source_range=self.location(node),
                    ),
                ),
            ),
        )

    def add(self, entity):
        if len(self.entities) >= 50_000:
            raise AdapterError(
                "vbscript",
                "analyze",
                (
                    AdapterIssue(
                        self.source.file.path,
                        SourceDiagnostic(
                            severity="ERROR",
                            code="vbscript.RESOURCE_LIMIT",
                            message="VBScript output exceeds 50000 facts",
                            source_range=entity.source_range,
                        ),
                    ),
                ),
            )
        if entity.id in self.entities:
            raise ValueError("duplicate VBScript declaration/fact: " + entity.name)
        self.entities[entity.id] = entity
        return entity

    def relation(self, source, target, node, rk, cap, reason=None):
        targets = target if isinstance(target, list) else [target] if target else []
        status = (
            "PARTIAL"
            if reason and targets
            else "RESOLVED"
            if len(targets) == 1
            else "UNRESOLVED"
        )
        key = self.key(
            f"relation:{rk}:{source.id}:" + ":".join(t.id for t in targets), node
        )
        resolution = (
            Resolution(status=status, target=_ref(targets[0]))
            if status == "RESOLVED"
            else Resolution(
                status=status,
                candidates=tuple(_ref(t) for t in targets),
                reason=reason or "no local target",
            )
        )
        return self.add(
            Relation(
                **self.env(EntityType.RELATION, key, rk.value, node),
                relation_kind=rk,
                source=_ref(source),
                resolution=resolution,
                certainty=Certainty.INFERRED if targets else Certainty.UNKNOWN,
                evidence=(
                    Evidence(
                        source_range=self.location(node),
                        analyzer="vbscript",
                        analyzer_version="1",
                        rule=rk.value.casefold(),
                        description=reason
                        or "Captured VBScript syntax; no runtime proof",
                    ),
                ),
                coverage=cap,
            )
        )

    def occurrence(self, node, frame, occ_kind, symbol=None):
        key = self.key("occurrence:" + occ_kind, node)
        entity_id = logical_id(
            self.source.file.repository_id, EntityType.OCCURRENCE, key
        )
        if entity_id in self.entities:
            return self.entities[entity_id]
        occurrence = self.add(
            Occurrence(
                **self.env(
                    EntityType.OCCURRENCE, key, self.mapping.text_of(node), node
                ),
                occurrence_kind=occ_kind,
                scope_id=frame.scope.id,
                resolution="RESOLVED" if symbol else "UNRESOLVED",
                target_symbol_id=symbol.id if symbol else None,
            )
        )
        if symbol:
            rk = (
                RelationKind.DECLARES
                if occ_kind == "DECLARATION"
                else RelationKind.REFERENCES
            )
            self.relation(occurrence, symbol, node, rk, self.caps[1])
        return occurrence

    def frame(self, scope_kind, owner, node, parent=None, top=False, result_name=None):
        scope = self.add(
            Scope(
                **self.env(
                    EntityType.SCOPE,
                    self.key("scope:" + scope_kind + ":" + owner.id, node),
                    scope_kind,
                    node,
                ),
                scope_kind=scope_kind,
                parent_scope_id=parent.scope.id if parent else None,
                owner_symbol_id=owner.id,
            )
        )
        frame = _Frame(scope, owner, parent, top=top, result_name=result_name)
        return frame

    def bind(self, frame, name, symbol, node):
        if name in frame.bindings:
            self.fail("duplicate case-insensitive declaration: " + name, node)
        frame.bindings[name] = symbol
        self.occurrence(node, frame, "DECLARATION", symbol)
        self.relation(frame.scope, symbol, node, RelationKind.CONTAINS, self.caps[1])

    def variable(self, identifier, frame, symbol_kind=None):
        name = identifier.getText().casefold()
        storage = frame.parent if frame.top else frame
        while storage.scope.scope_kind == "BLOCK":
            storage = storage.parent
        if symbol_kind is None:
            found = frame.lookup(name)
            if found:
                return found
            if self.explicit:
                raise ValueError("Option Explicit: undeclared assignment " + name)
        if symbol_kind is not None and name in storage.bindings:
            self.fail("duplicate case-insensitive declaration: " + name, identifier)
        etype = symbol_kind or (
            "FIELD" if storage.scope.scope_kind == "TYPE" else "LOCAL_VARIABLE"
        )
        key = storage.scope.logical_key + ":variable:" + name
        symbol = self.add(
            Symbol(
                **self.env(EntityType.SYMBOL, key, name, identifier),
                symbol_kind=etype,
                qualified_name=storage.owner.qualified_name + "." + name,
                scope_id=storage.scope.id,
                type_ref=TypeRef(name="vbscript.Variant"),
            )
        )
        self.bind(storage, name, symbol, identifier)
        return symbol

    def declare(self, block, frame):
        self.frames[id(block)] = frame
        for statement in block.statement():
            self.declaration(_children(statement)[0], frame)

    def declaration(self, node, frame):
        k = _kind(node)
        self.frames[id(node)] = frame
        if k in ("ClassDeclaration", "ProcedureDeclaration"):
            parent = frame.parent if frame.top else frame
            if parent.scope.scope_kind != "TYPE":
                raise ValueError("nested class/procedure declaration is unsupported")
            name_node = node.identifier()
            name = name_node.getText().casefold()
            actual_name = (
                name + "." + node.accessor().getText().casefold()
                if k == "ProcedureDeclaration" and node.accessor()
                else name
            )
            if actual_name in parent.bindings:
                self.fail(
                    "duplicate case-insensitive declaration: " + actual_name, name_node
                )
            if k == "ClassDeclaration":
                if parent.owner.id in self.types:
                    self.fail("nested VBScript classes are unsupported", name_node)
                key = self.source.file.path + ":class:" + name
                symbol = self.add(
                    Symbol(
                        **self.env(EntityType.SYMBOL, key, name, node),
                        symbol_kind="CLASS",
                        qualified_name=name,
                        scope_id=parent.scope.id,
                    )
                )
                child = self.frame("TYPE", symbol, node, parent)
                self.types[symbol.id] = child
            else:
                accessor = node.accessor()
                actual_name = (
                    name + "." + accessor.getText().casefold() if accessor else name
                )
                params = node.parameters().parameter() if node.parameters() else []
                signature = CallableSignature(
                    parameter_types=tuple(
                        TypeRef(name="vbscript.Variant") for _ in params
                    ),
                    return_type=TypeRef(
                        name="vbscript.Variant"
                        if node.FUNCTION() or (accessor and accessor.GET())
                        else "void"
                    ),
                )
                key = callable_key(parent.owner.logical_key, actual_name, signature)
                symbol = self.add(
                    Symbol(
                        **self.env(EntityType.SYMBOL, key, actual_name, node),
                        symbol_kind="METHOD",
                        qualified_name=parent.owner.qualified_name + "." + actual_name,
                        owner_key=parent.owner.logical_key,
                        signature=signature,
                        scope_id=parent.scope.id,
                    )
                )
                child = self.frame("CALLABLE", symbol, node, parent, result_name=name)
                for parameter in params:
                    self.variable(parameter.identifier(), child, "PARAMETER")
            self.bind(parent, symbol.name, symbol, name_node)
            self.frames[id(node)] = child
            self.bodies.append((node.block(), child))
            self.declare(node.block(), child)
            return
        if k == "SimpleStatement":
            if node.DIM() or node.PUBLIC() or node.PRIVATE():
                for variable in node.variable():
                    self.variable(
                        variable.identifier(),
                        frame,
                        "FIELD"
                        if frame.top or frame.scope.scope_kind == "TYPE"
                        else "LOCAL_VARIABLE",
                    )
            if node.REDIM():
                for variable in node.variable():
                    if frame.lookup(variable.identifier().getText().casefold()) is None:
                        self.variable(
                            variable.identifier(),
                            frame,
                            "FIELD" if frame.top else "LOCAL_VARIABLE",
                        )
            for constant in node.constant():
                self.variable(
                    constant.identifier(),
                    frame,
                    "FIELD"
                    if frame.top or frame.scope.scope_kind == "TYPE"
                    else "LOCAL_VARIABLE",
                )
            if (
                self.assignment(node)
                and not node.target().suffix()
                and not node.target().getText().startswith(".")
            ):
                name = node.target().identifier().getText().casefold()
                if name != frame.result_name:
                    self.variable(node.target().identifier(), frame)
            return
        if k == "ForStatement":
            self.variable(node.identifier(0), frame)
        blocks = [c for c in _children(node) if _kind(c) == "Block"]
        for block in blocks:
            self.declare(block, self.frame("BLOCK", frame.owner, block, frame))
        for simple in [c for c in _children(node) if _kind(c) == "SimpleStatement"]:
            self.declaration(simple, frame)

    @staticmethod
    def assignment(node):
        return node.target() is not None and any(
            c.getText() == "=" for c in node.children
        )

    def invalidate(self, env):
        self.epoch += 1
        env.clear()
        env.update(self.constants)

    def unknown(self, node):
        return _Value(
            (
                SqlFragment(
                    kind="DYNAMIC", text="__unknown__", source_range=self.location(node)
                ),
            ),
            reasons=("dynamic or unsupported VBScript value/flow",),
        )

    def sql(self, value, node, frame):
        if not value.fragments or not looks_like_sql(value.text):
            return None
        if len(value.text) > 65_536 or value.text.count(";") > 128:
            self.fail(
                "SQL recovery budget exceeded (65536 characters / 128 separators)",
                node,
                "RESOURCE_LIMIT",
            )
        key = self.key("sql", node)
        eid = logical_id(
            self.source.file.repository_id, EntityType.SQL_CONSTRUCTION, key
        )
        if eid in self.constructions:
            return self.constructions[eid]
        candidate = self.add(
            CodeEntity(
                **self.env(
                    EntityType.SQL_CANDIDATE, key + ":candidate", value.text, node
                ),
                entity_type=EntityType.SQL_CANDIDATE,
            )
        )
        construction = self.add(
            SqlConstruction(
                **self.env(EntityType.SQL_CONSTRUCTION, key, value.text, node),
                owner_symbol_id=frame.owner.id,
                variants=(
                    SqlVariant(
                        candidate_id=candidate.id,
                        text=value.text,
                        partial=bool(value.reasons),
                        partial_reasons=value.reasons,
                        fragments=value.fragments,
                    ),
                ),
            )
        )
        self.constructions[construction.id] = construction
        self.relation(
            frame.owner, construction, node, RelationKind.CONSTRUCTS_SQL, self.caps[3]
        )
        self.relation(
            construction, candidate, node, RelationKind.HAS_SQL_CANDIDATE, self.caps[3]
        )
        return construction

    def expression(self, node, frame, env):
        values = [self.unary(part, frame, env) for part in node.unaryExpression()]
        operators = [op.getText().casefold() for op in node.binaryOperator()]
        if not operators:
            value = values[0]
        elif all(op == "&" for op in operators) or (
            all(op in ("&", "+") for op in operators)
            and all(value.known and isinstance(value.literal, str) for value in values)
        ):
            safe = [v if v.fragments else self.unknown(node) for v in values]
            if (
                sum(len(v.fragments) for v in safe) > 128
                or sum(len(f.text) for v in safe for f in v.fragments) > 65_536
            ):
                self.fail(
                    "VBScript concatenation recovery budget exceeded",
                    node,
                    "RESOURCE_LIMIT",
                )
            fragments = tuple(f for v in safe for f in v.fragments)
            reasons = tuple(dict.fromkeys(r for v in safe for r in v.reasons))
            value = _Value(
                fragments,
                "".join(f.text for f in fragments) if not reasons else None,
                not reasons,
                reasons=reasons,
            )
        else:
            value = self.unknown(node)
            # Unsupported operators cannot hide an otherwise visible SQL literal;
            # those candidates are not attached to the call's unknown result.
            for part, candidate in zip(node.unaryExpression(), values, strict=True):
                self.sql(candidate, part, frame)
        self.sql(value, node, frame)
        return value

    def property_key(self, value, name):
        return f"@{value.object_id}.{name}" if value.object_id else None

    def unary(self, node, frame, env):
        atom = node.atom()
        identifier = atom.identifier()
        name = identifier.getText().casefold() if identifier else "<expression>"
        if atom.getText().startswith("."):
            name = "." + name
        symbol = frame.lookup(name) if identifier and not name.startswith(".") else None
        if atom.STRING():
            text = atom.STRING().getText()[1:-1].replace('""', '"')
            value = _Value(
                (
                    SqlFragment(
                        kind="STATIC", text=text, source_range=self.location(atom)
                    ),
                ),
                text,
                True,
            )
        elif atom.NUMBER():
            text = atom.NUMBER().getText()
            try:
                number = (
                    int(text[2:], 16 if text[:2].casefold() == "&h" else 8)
                    if text.startswith("&")
                    else int(text)
                )
                value = _Value(
                    (
                        SqlFragment(
                            kind="STATIC",
                            text=str(number),
                            source_range=self.location(atom),
                        ),
                    ),
                    number,
                    True,
                )
            except ValueError:
                value = self.unknown(atom)
        elif (
            atom.TRUE() or atom.FALSE() or atom.NOTHING() or atom.NULL() or atom.EMPTY()
        ):
            value = _Value(
                literal=True if atom.TRUE() else False if atom.FALSE() else None,
                known=True,
            )
        elif atom.expression():
            value = self.expression(atom.expression(), frame, env)
        elif atom.NEW():
            # Class_Initialize can mutate globals; its body is not evaluated here.
            self.invalidate(env)
            value = (
                _Value(
                    object_type="local:" + symbol.id, object_id=self.key("new", atom)
                )
                if symbol and symbol.symbol_kind == "CLASS"
                else self.unknown(atom)
            )
        else:
            value = (
                env.get(symbol.id, self.unknown(atom)) if symbol else self.unknown(atom)
            )
            if name == "me" and not symbol:
                current = frame
                while current and current.owner.id not in self.types:
                    current = current.parent
                if current:
                    value = _Value(
                        object_type="local:" + current.owner.id,
                        object_id="me:" + current.owner.id,
                    )
        if identifier and (not node.suffix() or atom.NEW()):
            occurrence = self.occurrence(identifier, frame, "READ", symbol)
            if atom.NEW() and symbol is None:
                self.external(
                    occurrence,
                    name,
                    atom,
                    "class is not declared in this VBScript file; host composition is unresolved",
                )
        if len([c for c in node.children if not isinstance(c, ParserRuleContext)]) > 0:
            value = self.unknown(node)
        return self.suffixes(
            node, name, identifier, symbol, value, node.suffix(), frame, env, False
        )

    def suffixes(
        self, node, name, identifier, symbol, value, suffixes, frame, env, force
    ):
        member = None
        receiver = None
        selector = name
        for i, suffix in enumerate(suffixes):
            if suffix.identifier():
                member = suffix.identifier()
                selector += "." + member.getText().casefold()
                receiver = value
                if i + 1 == len(suffixes) or suffixes[i + 1].identifier():
                    self.occurrence(member, frame, "REFERENCE")
                    value = env.get(
                        self.property_key(receiver, member.getText().casefold()),
                        self.unknown(suffix),
                    )
                    if force and i + 1 == len(suffixes):
                        return self.call(
                            node, selector, member, None, receiver, [], frame, env
                        )
                continue
            epoch = self.epoch
            args = self.arguments(suffix.arguments(), frame, env)
            if self.epoch != epoch:
                receiver = None
            end = suffix.stop.stop + 1
            region = (node.start.start, end)
            target_symbol = symbol if member is None else None
            value = self.call(
                region,
                selector,
                member or identifier,
                target_symbol,
                receiver,
                args,
                frame,
                env,
            )
            member, receiver, symbol = None, None, None
            selector += "()"
        if force and (not suffixes or suffixes[-1].identifier()):
            return self.call(
                node, selector, member or identifier, symbol, receiver, [], frame, env
            )
        return value

    def arguments(self, node, frame, env):
        if node is None:
            return []
        # Keep omitted arguments in their original positions.
        args, slot = [], None
        for child in node.children:
            if _kind(child) == "Expression":
                slot = (self.expression(child, frame, env), child)
            elif child.getText() == ",":
                args.append(slot or (self.unknown(node), node))
                slot = None
        args.append(slot or (self.unknown(node), node))
        return args

    def external(self, operation, selector, node, reason):
        self.add(
            ExternalReference(
                **self.env(
                    EntityType.EXTERNAL_REFERENCE,
                    self.key("external:" + operation.id, node),
                    selector,
                    node,
                ),
                source=_ref(operation),
                selector=SymbolSelector(qualified_name=selector.casefold()),
                reason=reason,
                evidence=(
                    Evidence(
                        source_range=self.location(node),
                        analyzer="vbscript",
                        analyzer_version="1",
                        rule="late-bound-call",
                        description=reason,
                    ),
                ),
                certainty=Certainty.UNKNOWN,
                coverage=self.caps[2],
            )
        )

    def call(self, node, selector, identifier, symbol, receiver, args, frame, env):
        if (
            receiver
            and receiver.object_type
            and receiver.object_type.startswith("local:")
        ):
            type_frame = self.types.get(receiver.object_type[6:])
            symbol = (
                type_frame.bindings.get(identifier.getText().casefold())
                if type_frame and identifier
                else None
            )
        target = (
            symbol
            if symbol
            and symbol.symbol_kind in ("METHOD", "CONSTRUCTOR")
            and len(symbol.signature.parameter_types) == len(args)
            else None
        )
        if self.dynamic:
            target_reason = "dynamic code may change local dispatch"
        else:
            target_reason = None
        api = selector
        method = identifier.getText().casefold() if identifier else "<expression>"
        if receiver and receiver.object_type in _ADO.values():
            api = (
                receiver.object_type
                + "."
                + {"execute": "Execute", "open": "Open"}.get(method, method)
            )
        values = [
            self.add(
                Value(
                    **self.env(
                        EntityType.VALUE,
                        self.key(f"argument:{selector}:{i}", node),
                        "argument",
                        arg,
                    ),
                    value_kind="LITERAL" if value.known else "UNKNOWN",
                    literal=value.literal if value.known else None,
                    partial=not value.known,
                )
            )
            for i, (value, arg) in enumerate(args)
        ]
        operation = self.add(
            Operation(
                **self.env(
                    EntityType.OPERATION, self.key("call:" + selector, node), api, node
                ),
                operation_kind="CALL",
                scope_id=frame.scope.id,
                input_value_ids=tuple(v.id for v in values),
                callee=TypeRef(
                    name=api,
                    resolution="RESOLVED"
                    if target and not self.dynamic
                    else "UNRESOLVED",
                    target_symbol_id=target.id if target and not self.dynamic else None,
                ),
            )
        )
        if identifier:
            self.occurrence(
                identifier, frame, "CALL", target if not self.dynamic else None
            )
        self.relation(
            operation,
            target,
            node,
            RelationKind.CALLS,
            self.caps[2],
            target_reason
            if target
            else "late-bound/unknown target or incompatible arity",
        )
        if target:
            self.invalidate(env)
            return self.unknown(node)
        self.external(
            operation,
            selector,
            node,
            "late-bound COM/host/dynamic dispatch; no runtime target is assumed",
        )
        is_creator = (
            selector == "createobject"
            and symbol is None
            and receiver is None
            and not self.dynamic
        )
        if is_creator:
            progid = args[0][0].literal if args and args[0][0].known else None
            return (
                _Value(
                    object_type=_ADO.get(progid.casefold()),
                    object_id=self.key("com", node),
                )
                if isinstance(progid, str)
                else self.unknown(node)
            )
        sink = bool(
            receiver
            and (
                (receiver.object_type == "ADODB.Connection" and method == "execute")
                or (receiver.object_type == "ADODB.Recordset" and method == "open")
                or (receiver.object_type == "ADODB.Command" and method == "execute")
            )
        )
        if sink:
            key = self.key("execution", node)
            command = receiver.object_type == "ADODB.Command"
            execution = self.add(
                SqlExecute(
                    **self.env(EntityType.SQL_EXECUTE, key, api, node),
                    owner_symbol_id=frame.owner.id,
                    operation_id=operation.id,
                    api=api,
                    sql_argument_index=0 if args and not command else None,
                )
            )
            self.relation(
                frame.owner, execution, node, RelationKind.EXECUTES_SQL, self.caps[5]
            )
            sql_value = (
                env.get(self.property_key(receiver, "commandtext"), self.unknown(node))
                if command
                else args[0][0]
                if args
                else self.unknown(node)
            )
            options = (
                env.get(self.property_key(receiver, "commandtype"))
                if command
                else args[4 if method == "open" else 2][0]
                if len(args) > (4 if method == "open" else 2)
                else None
            )
            allowed = (
                (
                    options is not None
                    and options.known
                    and type(options.literal) is int
                    and options.literal == 1
                )
                if command
                else options is None
                or (
                    options.known
                    and type(options.literal) is int
                    and options.literal & 15 in (0, 1, 8)
                )
            )
            construction = (
                self.sql(sql_value, args[0][1] if args and not command else node, frame)
                if allowed
                else None
            )
            if construction:
                self.relation(
                    execution,
                    construction,
                    node,
                    RelationKind.USES_SQL_CONSTRUCTION,
                    self.caps[5],
                )
                self.executions.append((execution, construction, node))
            affected = 0 if command else 1
            if method == "execute" and len(args) > affected:
                out_node = args[affected][1]
                if (
                    _kind(out_node) == "Expression"
                    and not out_node.binaryOperator()
                    and len(out_node.unaryExpression()) == 1
                ):
                    part = out_node.unaryExpression(0)
                    identifier_node = part.atom().identifier()
                    binding = (
                        frame.lookup(identifier_node.getText().casefold())
                        if identifier_node and not part.suffix()
                        else None
                    )
                    if binding:
                        env.pop(binding.id, None)
                    else:
                        self.invalidate(env)
                else:
                    self.invalidate(env)
            return self.unknown(node)
        if not (
            receiver
            and receiver.object_type == "ADODB.Connection"
            and method
            in {"open", "close", "begintrans", "committrans", "rollbacktrans"}
        ):
            self.invalidate(env)
        return self.unknown(node)

    def target_receiver(self, node, frame, env):
        name = node.identifier().getText().casefold()
        symbol = frame.lookup(name)
        receiver = (
            env.get(symbol.id, self.unknown(node)) if symbol else self.unknown(node)
        )
        return symbol, receiver

    def simple(self, node, frame, env):
        if node.constant():
            for constant in node.constant():
                symbol = frame.lookup(constant.identifier().getText().casefold())
                value = self.expression(constant.expression(), frame, env)
                if not value.known:
                    self.fail(
                        "unsupported nonconstant VBScript Const initializer", constant
                    )
                env[symbol.id] = value
                self.constants[symbol.id] = value
            return
        if self.assignment(node):
            value = self.expression(node.expression(), frame, env)
            target = node.target()
            if target.getText().startswith("."):
                self.occurrence(target.identifier(), frame, "WRITE")
                return
            symbol, receiver = self.target_receiver(target, frame, env)
            if not target.suffix():
                if target.identifier().getText().casefold() == frame.result_name:
                    symbol = frame.owner
                if symbol:
                    if symbol.id in self.constants:
                        self.fail("assignment to a VBScript Const", target)
                    self.occurrence(target.identifier(), frame, "WRITE", symbol)
                    env[symbol.id] = value
            elif len(target.suffix()) == 1 and target.suffix()[0].identifier():
                member = target.suffix()[0].identifier()
                self.occurrence(member, frame, "WRITE")
                key = self.property_key(receiver, member.getText().casefold())
                if key:
                    env[key] = value
            else:
                self.invalidate(env)
            return
        if node.target():
            target = node.target()
            symbol, value = self.target_receiver(target, frame, env)
            if target.getText().startswith("."):
                symbol = None
            name = (
                "." if target.getText().startswith(".") else ""
            ) + target.identifier().getText().casefold()
            if node.arguments():
                epoch = self.epoch
                args = self.arguments(node.arguments(), frame, env)
                if self.epoch != epoch:
                    value = self.unknown(target)
                suffixes = target.suffix()
                receiver = (
                    value
                    if len(suffixes) == 1
                    and suffixes[0].identifier()
                    and not target.getText().startswith(".")
                    else None
                )
                identifier = (
                    suffixes[-1].identifier()
                    if suffixes and suffixes[-1].identifier()
                    else target.identifier()
                )
                self.call(
                    node,
                    target.getText().casefold(),
                    identifier,
                    symbol if not suffixes else None,
                    receiver,
                    args,
                    frame,
                    env,
                )
            else:
                self.suffixes(
                    target,
                    name,
                    target.identifier(),
                    symbol,
                    value,
                    target.suffix(),
                    frame,
                    env,
                    True,
                )
        elif node.ON() or node.EXIT() or node.REDIM() or node.ERASE():
            self.invalidate(env)

    def flow(self, block, frame, env):
        for statement in block.statement():
            node = _children(statement)[0]
            k = _kind(node)
            if k in ("ClassDeclaration", "ProcedureDeclaration"):
                continue
            if k == "SimpleStatement":
                if frame.scope.scope_kind == "TYPE" and not (
                    node.constant() or node.variable()
                ):
                    raise ValueError(
                        "executable statement directly in a VBScript class"
                    )
                self.simple(node, frame, env)
                continue
            if frame.scope.scope_kind == "TYPE":
                self.fail(
                    "control flow directly in a VBScript class is unsupported", node
                )
            # Never propagate a guessed branch/loop reaching definition.
            constants = dict(self.constants)
            self.invalidate(env)
            for child in _children(node):
                if _kind(child) == "Expression":
                    self.expression(child, frame, dict(env))
                elif _kind(child) == "Block":
                    self.flow(child, self.frames[id(child)], dict(env))
                elif _kind(child) == "SimpleStatement":
                    self.simple(child, frame, dict(env))
            self.constants = constants
            self.invalidate(env)

    def build(self):
        region = (0, len(self.mapping.text))
        key = self.source.file.path + ":script"
        script = self.add(
            Symbol(
                **self.env(EntityType.SYMBOL, key, "<script>", region),
                symbol_kind="CLASS",
                qualified_name=f"<script:{self.source.file.path}>",
            )
        )
        root = self.frame("FILE", script, region)
        script_frame = self.frame("TYPE", script, region, root)
        signature = CallableSignature()
        run = self.add(
            Symbol(
                **self.env(
                    EntityType.SYMBOL,
                    callable_key(key, "<run>", signature),
                    "<run>",
                    region,
                ),
                symbol_kind="METHOD",
                qualified_name=script.qualified_name + ".<run>",
                owner_key=key,
                signature=signature,
                scope_id=script_frame.scope.id,
            )
        )
        frame = self.frame("CALLABLE", run, region, script_frame, top=True)
        self.declare(self.tree.block(), frame)
        self.flow(self.tree.block(), frame, {})
        for body, owner in self.bodies:
            self.flow(body, owner, dict(self.constants))
        statements = {}
        for construction in self.constructions.values():
            semantics, indexed = semantic_constructions(
                {construction.id: construction},
                self.source.file.repository_id,
                self.dialect,
                self.caps[4],
            )
            statements.update(indexed)
            for entity in semantics:
                if isinstance(entity, Relation):
                    entity = entity.model_copy(
                        update={
                            "evidence": tuple(
                                e.model_copy(
                                    update={
                                        "description": e.description.replace(
                                            "Java origin", "VBScript origin"
                                        )
                                    }
                                )
                                for e in entity.evidence
                            )
                        }
                    )
                self.add(entity)
                if (
                    entity.entity_type == EntityType.SQL_STATEMENT
                    and entity.parse_status != "COMPLETE"
                ):
                    self.diagnostics.append(
                        SourceDiagnostic(
                            severity="WARNING",
                            code="vbscript.SQL_" + entity.parse_status,
                            message="; ".join(entity.reasons),
                            source_range=entity.source_range,
                        )
                    )
        for execution, construction, node in self.executions:
            for statement in statements[construction.id]:
                self.relation(
                    execution,
                    statement,
                    node,
                    RelationKind.EXECUTES_STATEMENT,
                    self.caps[5],
                    None
                    if statement.parse_status == "COMPLETE"
                    and not construction.variants[0].partial
                    else "partial SQL construction or parse",
                )
        return AdapterFileResult(
            analysis=FileAnalysis(
                path=self.source.file.path, entities=tuple(self.entities.values())
            ),
            capabilities=self.caps,
            diagnostics=tuple(self.diagnostics),
        )


def extract_vbscript(
    source: SourceInput, dialect: str = "postgres"
) -> AdapterFileResult:
    """Analyze one file without ambient context; failures retain structured diagnostics."""
    parsed = parse_vbscript(source)
    if parsed.diagnostics:
        raise AdapterError(
            "vbscript",
            "analyze",
            tuple(AdapterIssue(source.file.path, d) for d in parsed.diagnostics),
        )
    try:
        return _Extract(source, parsed, dialect).build()
    except (ValueError, RecursionError) as error:
        raise AdapterError(
            "vbscript",
            "analyze",
            (
                AdapterIssue(
                    source.file.path,
                    SourceDiagnostic(
                        severity="ERROR",
                        code="vbscript.EXTRACTION_ERROR",
                        message=str(error) or "VBScript extraction nesting limit",
                    ),
                ),
            ),
        ) from error
