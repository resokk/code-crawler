"""Bounded lexical Groovy facts and non-executing SQL recovery over ANTLR."""

import re
from dataclasses import dataclass, field

from antlr4 import ParserRuleContext

from code_crawler.groovy_parse import GroovySourceMap, parse_groovy
from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.java_semantic import semantic_constructions
from code_crawler.source_adapters import AdapterFileResult
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
    Relation,
    RelationKind,
    Resolution,
    Scope,
    SourceDiagnostic,
    SqlConstruction,
    SqlFragment,
    SqlVariant,
    Symbol,
    SymbolSelector,
    TypeRef,
    callable_key,
    logical_id,
)

LIMITS = "syntax-only Groovy; MOP, generated members, dispatch and control flow are not resolved"


def capabilities(error: bool = False) -> tuple[Coverage, ...]:
    return tuple(
        Coverage(
            capability=name,
            analyzer_version="1",
            status=("PARTIAL" if error else "COMPLETE")
            if i == 0
            else ("UNSUPPORTED" if error else "PARTIAL"),
            reasons=("invalid Groovy source; semantic facts suppressed",)
            if error
            else (() if i == 0 else (LIMITS,)),
        )
        for i, name in enumerate(
            (
                "groovy.parser.diagnostics",
                "groovy.symbols",
                "groovy.references",
                "groovy.sql.construction",
                "sql.semantic.access",
            )
        )
    )


def _children(node):
    return [
        c
        for c in (getattr(node, "children", None) or [])
        if isinstance(c, ParserRuleContext)
    ]


def _kind(node):
    return type(node).__name__.removesuffix("Context")


def _desc(node, kind):
    for child in _children(node):
        if _kind(child) == kind:
            yield child
        else:
            yield from _desc(child, kind)


@dataclass
class _Frame:
    scope: Scope
    parent: "_Frame | None"
    owner: Symbol | None
    bindings: dict[str, list] = field(default_factory=dict)
    barrier: bool = False
    closure: bool = False


@dataclass
class _Binding:
    symbol: Symbol
    node: ParserRuleContext
    initializer: ParserRuleContext | None = None
    constant: bool = False
    writes: bool = False


@dataclass(frozen=True)
class _Value:
    fragments: tuple[SqlFragment, ...]
    reasons: tuple[str, ...] = ()
    string: bool = True

    @property
    def text(self) -> str:
        return "".join(f.text for f in self.fragments)


class _Extract:
    def __init__(self, source: SourceInput, mapping: GroovySourceMap):
        self.source, self.mapping = source, mapping
        self.entities = {}
        self.frames = {}
        self.bindings = []
        self.constructions = {}
        self.active = set()

    def env(self, kind, key, name, node=None):
        return {
            "repository_id": self.source.file.repository_id,
            "logical_key": key,
            "id": logical_id(self.source.file.repository_id, kind, key),
            "name": name,
            "source_range": self.mapping.range(node) if node is not None else None,
        }

    def add(self, entity):
        if entity.id in self.entities:
            raise ValueError("duplicate declaration identity: " + entity.name)
        self.entities[entity.id] = entity
        return entity

    def key(self, tag, node):
        return f"{self.source.file.path}:{tag}:{node.start.start}"

    def scope(self, kind, node, parent, owner):
        scope = self.add(
            Scope(
                **self.env(
                    EntityType.SCOPE,
                    self.key(
                        "scope:" + kind + ":" + (owner.id if owner else "root"), node
                    ),
                    kind,
                    node,
                ),
                scope_kind=kind,
                parent_scope_id=parent.scope.id if parent else None,
                owner_symbol_id=owner.id if owner else None,
            )
        )
        return _Frame(scope, parent, owner)

    def occurrence(self, node, frame, kind, binding=None):
        name = self.mapping.text_of(node)
        key = self.key("occurrence:" + kind, node)
        if (
            logical_id(self.source.file.repository_id, EntityType.OCCURRENCE, key)
            in self.entities
        ):
            return
        occurrence = self.add(
            Occurrence(
                **self.env(EntityType.OCCURRENCE, key, name or kind, node),
                occurrence_kind=kind,
                scope_id=frame.scope.id,
                resolution="RESOLVED" if binding else "UNRESOLVED",
                target_symbol_id=binding.symbol.id if binding else None,
            )
        )

        if binding:
            self.relation(
                occurrence,
                binding.symbol,
                node,
                RelationKind.DECLARES
                if kind == "DECLARATION"
                else RelationKind.REFERENCES,
                capabilities()[1 if kind == "DECLARATION" else 2],
            )

    def relation(self, origin, target, node, kind, coverage):
        self.add(
            Relation(
                **self.env(
                    EntityType.RELATION,
                    self.key("relation:" + kind.value + ":" + target.id, node),
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
                        source_range=self.mapping.range(node),
                        analyzer="groovy",
                        analyzer_version="1",
                        rule=kind.value,
                        description="lexical syntax fact",
                    ),
                ),
                coverage=coverage,
            )
        )

    def declare(
        self,
        name_node,
        kind,
        frame,
        node,
        initializer=None,
        type_name=None,
        constant=False,
    ):
        name = name_node.getText()
        symbol = self.add(
            Symbol(
                **self.env(
                    EntityType.SYMBOL, self.key(kind, name_node), name, name_node
                ),
                symbol_kind=kind,
                qualified_name=(frame.owner.qualified_name + "." if frame.owner else "")
                + name,
                scope_id=frame.scope.id,
                type_ref=TypeRef(name=type_name or "groovy.dynamic"),
            )
        )
        binding = _Binding(symbol, node, initializer, constant)
        frame.bindings.setdefault(name, []).append(binding)
        self.bindings.append(binding)
        self.occurrence(name_node, frame, "DECLARATION", binding)
        return binding

    def walk(self, node, frame):
        kind = _kind(node)
        if kind == "ClassDeclaration":
            name_node = node.identifier()
            name = name_node.getText()
            owner = self.add(
                Symbol(
                    **self.env(
                        EntityType.SYMBOL, self.key("type", node), name, name_node
                    ),
                    symbol_kind="CLASS",
                    qualified_name=name,
                    scope_id=frame.scope.id,
                )
            )
            self.occurrence(name_node, frame, "DECLARATION", _Binding(owner, node))
            parent = frame
            while parent.parent is not None and parent.scope.scope_kind not in (
                "TYPE",
                "FILE",
            ):
                parent = parent.parent
            frame = self.scope("TYPE", node, parent, owner)
        elif kind == "MethodDeclaration":
            name_node = node.methodName()
            name = name_node.getText().strip("'\"")
            parameter_list = node.formalParameters().formalParameterList()
            params = parameter_list.formalParameter() if parameter_list else []
            types = tuple(
                TypeRef(
                    name=(p.type_().getText() if p.type_() else "groovy.dynamic")
                    + ("[]" if p.ELLIPSIS() else "")
                )
                for p in params
            )
            owner = frame.owner
            if (
                frame.scope.scope_kind == "CALLABLE"
                and frame.parent is not None
                and owner.name == "run"
            ):
                owner = frame.parent.owner
            signature = CallableSignature(
                parameter_types=types,
                return_type=TypeRef(
                    name=node.returnType().getText()
                    if node.returnType()
                    else "groovy.dynamic"
                ),
            )
            symbol = self.add(
                Symbol(
                    **self.env(
                        EntityType.SYMBOL,
                        callable_key(owner.logical_key, name, signature),
                        name,
                        name_node,
                    ),
                    symbol_kind="CONSTRUCTOR"
                    if name == owner.name and not node.returnType()
                    else "METHOD",
                    qualified_name=owner.qualified_name + "." + name,
                    scope_id=frame.scope.id,
                    owner_key=owner.logical_key,
                    signature=signature,
                )
            )
            self.occurrence(name_node, frame, "DECLARATION", _Binding(symbol, node))
            # Script methods cannot capture the script run's local variables.
            parent = frame.parent if frame.scope.scope_kind == "CALLABLE" else frame
            frame = self.scope("CALLABLE", node, parent, symbol)
        elif kind in (
            "Block",
            "Closure",
            "ForStmtAlt",
            "CatchClause",
            "LambdaExpression",
            "StandardLambdaExpression",
        ):
            frame = self.scope("BLOCK", node, frame, frame.owner)
            frame.barrier = kind in (
                "ForStmtAlt",
                "CatchClause",
                "LambdaExpression",
                "StandardLambdaExpression",
            )
            frame.closure = kind == "Closure"
        self.frames[id(node)] = frame
        if kind == "FormalParameter":
            self.declare(
                node.variableDeclaratorId().identifier(),
                "PARAMETER",
                frame,
                node,
                type_name=node.type_().getText() if node.type_() else None,
            )
        elif kind == "VariableDeclaration":
            field_decl = _kind(node.parentCtx) == "FieldDeclaration"
            type_name = node.type_().getText() if node.type_() else None
            modifiers = node.modifiers()
            final = bool(
                modifiers and re.search(r"\bfinal\b", self.mapping.text_of(modifiers))
            )
            if node.typeNamePairs() is not None:
                raise ValueError(
                    "tuple declarations are outside Groovy lexical coverage"
                )
            for decl in _desc(node, "VariableDeclarator"):
                self.declare(
                    decl.variableDeclaratorId().identifier(),
                    "FIELD" if field_decl else "LOCAL_VARIABLE",
                    frame,
                    decl,
                    decl.variableInitializer(),
                    type_name,
                    final if field_decl else True,
                )
        for child in _children(node):
            self.walk(child, frame)

    def lookup(self, name, node, frame):
        while frame:
            matches = [
                b
                for b in frame.bindings.get(name, ())
                if b.symbol.symbol_kind in ("FIELD", "PARAMETER")
                or b.node.stop.stop < node.start.start
            ]
            if matches:
                return matches[-1] if len(matches) == 1 else None
            if frame.barrier or (frame.closure and name == "it"):
                return None
            frame = frame.parent
        return None

    def external(self, node, frame, name):
        owner = frame.owner
        reference = self.add(
            ExternalReference(
                **self.env(
                    EntityType.EXTERNAL_REFERENCE,
                    self.key("external", node),
                    name,
                    node,
                ),
                source=EntityRef(entity_type=EntityType.SYMBOL, id=owner.id),
                selector=SymbolSelector(qualified_name=name),
                reason=LIMITS,
                evidence=(
                    Evidence(
                        source_range=self.mapping.range(node),
                        analyzer="groovy.references",
                        analyzer_version="1",
                        rule="dynamic-dispatch",
                        description=LIMITS,
                    ),
                ),
                certainty=Certainty.UNKNOWN,
                coverage=capabilities()[2],
            )
        )
        self.relation(
            owner, reference, node, RelationKind.EXTERNAL_DEPENDENCY, capabilities()[2]
        )

    def references(self, node):
        frame = self.frames[id(node)]
        kind = _kind(node)
        if kind == "IdentifierPrmrAlt":
            name = node.identifier().getText()
            path = node.parentCtx
            elements = path.pathElement() if _kind(path) == "PathExpression" else []
            call = bool(
                elements
                and (elements[0].arguments() or elements[0].closureOrLambdaExpression())
            )
            command_root = path
            while command_root.parentCtx is not None and _kind(
                command_root.parentCtx
            ) in ("PostfixExpression", "PostfixExprAlt"):
                command_root = command_root.parentCtx
            command = command_root.parentCtx
            if (
                not elements
                and _kind(command) == "CommandExpression"
                and command.argumentList() is not None
            ):
                call = True
            binding = None if call else self.lookup(name, node, frame)
            assignment = node
            while assignment.parentCtx is not None and _kind(assignment.parentCtx) in (
                "PathExpression",
                "PostfixExpression",
                "PostfixExprAlt",
            ):
                assignment = assignment.parentCtx
            parent = assignment.parentCtx
            write = _kind(parent) == "AssignmentExprAlt" and parent.left is assignment
            inc = _kind(parent) in (
                "PostfixExprAlt",
                "UnaryNotExprAlt",
                "UnaryAddExprAlt",
            ) and any(x in parent.getText() for x in ("++", "--"))
            inc = inc or (
                not elements
                and _kind(assignment) == "PostfixExprAlt"
                and assignment.postfixExpression().op is not None
            )
            self.occurrence(
                node,
                frame,
                "CALL" if call else "WRITE" if write or inc else "READ",
                binding,
            )
            if binding and (write or inc):
                binding.writes = True
            if call:
                self.external(node, frame, name)
        elif kind == "GstringPath":
            binding = self.lookup(node.identifier().getText(), node, frame)
            self.occurrence(node.identifier(), frame, "READ", binding)
        elif kind == "PathElement" and node.namePart() is not None:
            elements = node.parentCtx.pathElement()
            index = elements.index(node)
            called = index + 1 < len(elements) and (
                elements[index + 1].arguments() is not None
                or elements[index + 1].closureOrLambdaExpression() is not None
            )
            self.occurrence(node.namePart(), frame, "CALL" if called else "REFERENCE")
            self.external(node, frame, self.mapping.text_of(node.parentCtx))
        for child in _children(node):
            self.references(child)

    def unknown(self, node):
        return _Value(
            (
                SqlFragment(
                    kind="DYNAMIC",
                    text="__unknown__",
                    source_range=self.mapping.range(node),
                ),
            ),
            ("unresolved Groovy value or flow",),
        )

    def literal(self, text, node):
        delimiter = next(
            (d for d in ("'''", '"""', "$/", "'", '"', "/") if text.startswith(d)), None
        )
        if delimiter is None:
            return self.unknown(node)
        close = "/$" if delimiter == "$/" else delimiter
        body = text[len(delimiter) : -len(close)]
        if delimiter == "$/":
            body = body.replace("$$", "\x00").replace("$/", "/").replace("\x00", "$")
        elif delimiter == "/":
            body = body.replace(r"\/", "/")
        else:
            escapes = {
                "n": "\n",
                "r": "\r",
                "t": "\t",
                "b": "\b",
                "f": "\f",
                "\\": "\\",
                "'": "'",
                '"': '"',
                "$": "$",
            }

            def decode(m):
                token = m.group(1)
                if token.startswith("u"):
                    return chr(int(token[1:], 16))
                if token in escapes:
                    return escapes[token]
                raise ValueError("unsupported escape")

            try:
                body = re.sub(r"\\(u[0-9a-fA-F]{4}|.)", decode, body, flags=re.DOTALL)
            except ValueError:
                return self.unknown(node)
        return _Value(
            (
                SqlFragment(
                    kind="STATIC", text=body, source_range=self.mapping.range(node)
                ),
            )
        )

    def value(self, node, depth=0):
        if depth > 40 or id(node) in self.active:
            return self.unknown(node)
        self.active.add(id(node))
        try:
            return self._value(node, depth)
        finally:
            self.active.remove(id(node))

    def _value(self, node, depth):
        kind = _kind(node)
        if kind == "StringLiteral":
            return self.literal(node.getText(), node)
        if kind == "Gstring":
            fragments, reasons = [], []
            tokens = node.children
            opening = tokens[0].getText()
            delimiter = next(
                d for d in ('"""', '"', "$/", "/") if opening.startswith(d)
            )
            close = "/$" if delimiter == "$/" else delimiter
            for i, part in enumerate(tokens):
                if isinstance(part, ParserRuleContext):
                    if _kind(part) == "GstringValue":
                        path = part.gstringPath()
                        if path is not None and not path.GStringPathPart():
                            value = self.name_value(
                                path.identifier().getText(), part, depth
                            )
                        elif part.closure() is not None and not part.closure().ARROW():
                            expressions = list(
                                _desc(part.closure(), "CommandExpression")
                            )
                            value = (
                                self.value(expressions[0], depth + 1)
                                if len(expressions) == 1
                                and self.mapping.text_of(part.closure())[1:-1]
                                .strip()
                                .rstrip(";")
                                .strip()
                                == self.mapping.text_of(expressions[0]).strip()
                                else self.unknown(part)
                            )
                        else:
                            value = self.unknown(part)
                        fragments.extend(value.fragments)
                        reasons.extend(value.reasons)
                else:
                    text = part.getText()
                    text = text[len(delimiter) :] if i == 0 else text
                    text = text[: -len(close)] if i == len(tokens) - 1 else text[:-1]
                    value = self.literal(delimiter + text + close, node)
                    fragments.extend(value.fragments)
                    reasons.extend(value.reasons)
            return _Value(tuple(fragments), tuple(dict.fromkeys(reasons)))
        if kind in ("IdentifierPrmrAlt", "GstringPath"):
            return self.name_value(node.identifier().getText(), node, depth)
        if kind in ("Literal", "IntegerLiteralAlt") and re.fullmatch(
            r"[0-9]+", node.getText()
        ):
            return _Value(
                (
                    SqlFragment(
                        kind="STATIC",
                        text=node.getText(),
                        source_range=self.mapping.range(node),
                    ),
                ),
                string=False,
            )
        if kind == "AdditiveExprAlt" and node.op.text == "+":
            left, right = (
                self.value(node.left, depth + 1),
                self.value(node.right, depth + 1),
            )
            if not left.string and not right.string:
                return self.unknown(node)
            return _Value(
                left.fragments + right.fragments,
                tuple(dict.fromkeys(left.reasons + right.reasons)),
            )
        children = _children(node)
        if len(children) == 1 and kind in (
            "VariableInitializer",
            "EnhancedStatementExpression",
            "StatementExpression",
            "CommandExprAlt",
            "CommandExpression",
            "PostfixExprAlt",
            "PostfixExpression",
            "PathExpression",
            "LiteralPrmrAlt",
            "GstringPrmrAlt",
            "Literal",
            "StringLiteralAlt",
            "IntegerLiteralAlt",
            "ParenPrmrAlt",
            "ParExpression",
        ):
            if kind == "PostfixExpression" and node.op is not None:
                return self.unknown(node)
            if kind == "PathExpression" and node.pathElement():
                return self.unknown(node)
            if kind == "CommandExpression" and node.argumentList() is not None:
                return self.unknown(node)
            return self.value(children[0], depth + 1)
        return self.unknown(node)

    def name_value(self, name, node, depth):
        binding = self.lookup(name, node, self.frames[id(node)])
        if binding and binding.constant and not binding.writes and binding.initializer:
            return self.value(binding.initializer, depth + 1)
        return self.unknown(node)

    def sql(self, node):
        kind = _kind(node)
        if kind in ("StringLiteral", "Gstring", "AdditiveExprAlt"):
            value = self.value(node)
            if looks_like_sql(value.text):
                key = self.key("sql", node)
                candidate = self.add(
                    CodeEntity(
                        **self.env(
                            EntityType.SQL_CANDIDATE,
                            key + ":candidate",
                            value.text,
                            node,
                        ),
                        entity_type=EntityType.SQL_CANDIDATE,
                    )
                )
                construction = self.add(
                    SqlConstruction(
                        **self.env(EntityType.SQL_CONSTRUCTION, key, value.text, node),
                        owner_symbol_id=self.frames[id(node)].owner.id,
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
                owner = self.entities[construction.owner_symbol_id]
                self.relation(
                    owner,
                    construction,
                    node,
                    RelationKind.CONSTRUCTS_SQL,
                    capabilities()[3],
                )
                self.relation(
                    construction,
                    candidate,
                    node,
                    RelationKind.HAS_SQL_CANDIDATE,
                    capabilities()[3],
                )
                # Prefer the assembled SQL over its nested literal prefixes.
                return
        for child in _children(node):
            self.sql(child)


def extract_groovy(source: SourceInput, dialect: str = "postgres") -> AdapterFileResult:
    parsed = parse_groovy(source)
    if parsed.diagnostics:
        return AdapterFileResult(
            analysis=FileAnalysis(path=source.file.path, entities=()),
            diagnostics=parsed.diagnostics,
            capabilities=capabilities(True),
        )
    extractor = _Extract(source, parsed.mapping)
    try:
        root = extractor.scope("FILE", parsed.tree, None, None)
        script_key = source.file.path + ":script"
        script = extractor.add(
            Symbol(
                **extractor.env(EntityType.SYMBOL, script_key, "<script>"),
                symbol_kind="CLASS",
                qualified_name="<script:" + source.file.path + ">",
                scope_id=root.scope.id,
            )
        )
        script_frame = extractor.scope("TYPE", parsed.tree, root, script)
        signature = CallableSignature()
        run = extractor.add(
            Symbol(
                **extractor.env(
                    EntityType.SYMBOL, callable_key(script_key, "run", signature), "run"
                ),
                symbol_kind="METHOD",
                qualified_name=script.qualified_name + ".run",
                owner_key=script_key,
                signature=signature,
                scope_id=script_frame.scope.id,
            )
        )
        frame = extractor.scope("CALLABLE", parsed.tree, script_frame, run)
        extractor.walk(parsed.tree, frame)
        if any(f.barrier for f in extractor.frames.values()):
            for binding in extractor.bindings:
                binding.writes = True
        extractor.references(parsed.tree)
        extractor.sql(parsed.tree)
        semantics, _ = semantic_constructions(
            extractor.constructions,
            source.file.repository_id,
            dialect,
            capabilities()[-1],
        )
        for entity in semantics:
            extractor.add(entity)
    except ValueError as error:
        return AdapterFileResult(
            analysis=FileAnalysis(path=source.file.path, entities=()),
            diagnostics=(
                SourceDiagnostic(
                    severity="ERROR", code="groovy.EXTRACTION_ERROR", message=str(error)
                ),
            ),
            capabilities=capabilities(True),
        )
    return AdapterFileResult(
        analysis=FileAnalysis(
            path=source.file.path, entities=tuple(extractor.entities.values())
        ),
        capabilities=capabilities(),
    )
