"""PL/Plus lexical symbols and CFT accesses, independent of physical SQL identity."""

import hashlib
import json
import re
from dataclasses import dataclass, field

from antlr4 import ParserRuleContext

from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.plplus_parse import PlplusParseResult, parse_plplus
from code_crawler.source_adapters import AdapterFileResult
from code_crawler.ucm import (
    CallableSignature,
    Certainty,
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
    Symbol,
    SymbolSelector,
    TypeRef,
    callable_key,
    logical_id,
)

_LIMITS = "syntax-only PL/Plus; macros, overload applicability and CFT metadata are not resolved"
_PATH = re.compile(
    r"^(?P<root>.*?)(?P<class>[^/]+)/(?P<group>methods|criteria)/(?P<member>[^/]+)/src/[^/]+\.plp$"
)
_QUERIES = {
    "SelectQuery": "READ",
    "LocateStatement": "READ",
    "InsertStatement": "INSERT",
    "UpdateStatement": "UPDATE",
    "DeleteStatement": "DELETE",
}
_CALLABLES = ("FunctionDeclaration", "ProcedureDeclaration")


def capabilities(error: bool = False) -> tuple[Coverage, ...]:
    return tuple(
        Coverage(
            capability=name,
            analyzer_version="1",
            status=("PARTIAL" if error else "COMPLETE")
            if i == 0
            else ("UNSUPPORTED" if error else "PARTIAL"),
            reasons=(
                "PL/Plus parsing or extraction incomplete; semantic facts suppressed",
            )
            if error
            else (() if i == 0 else (_LIMITS,)),
        )
        for i, name in enumerate(
            (
                "plplus.parser.diagnostics",
                "plplus.symbols",
                "plplus.calls",
                "plplus.cft.access",
            )
        )
    )


def _kind(node):
    return type(node).__name__.removesuffix("Context")


def _children(node):
    return [
        c
        for c in (getattr(node, "children", None) or [])
        if isinstance(c, ParserRuleContext)
    ]


def _desc(node, kind):
    for child in _children(node):
        if _kind(child) == kind:
            yield child
        else:
            yield from _desc(child, kind)


def _name(text):
    if text.startswith('"'):
        return text
    return text.upper()


def _bracket(text):
    return text[1:-1].strip().upper()


@dataclass
class _Frame:
    scope: Scope
    parent: "_Frame | None"
    owner: Symbol | None
    variables: dict[str, list] = field(default_factory=dict)
    functions: dict[str, list] = field(default_factory=dict)


@dataclass(frozen=True)
class _Function:
    symbol: Symbol
    path: str
    frame: _Frame
    top_level: bool
    body: bool


class _Unit:
    def __init__(self, source: SourceInput, parsed: PlplusParseResult):
        self.source, self.parsed, self.mapping = source, parsed, parsed.mapping
        self.entities = {}
        self.frames = {}
        self.functions = []
        self.dependencies = set()
        self.diagnostics = list(parsed.diagnostics)
        self.valid = not self.diagnostics
        self.path = _PATH.fullmatch(source.file.path)
        self.context = (
            (
                self.path["root"],
                _name(self.path["class"]),
                self.path["group"],
                _name(self.path["member"]),
            )
            if self.path
            else None
        )
        self.own_class = self.context[1] if self.context else None
        self.body_ids = set()

    def env(self, kind, key, name, node=None):
        return {
            "repository_id": self.source.file.repository_id,
            "logical_key": key,
            "id": logical_id(self.source.file.repository_id, kind, key),
            "name": name,
            "source_range": self.mapping.range(node) if node is not None else None,
        }

    def key(self, tag, node):
        return f"{self.source.file.path}:{tag}:{node.start.start}"

    def add(self, entity):
        if entity.id in self.entities:
            raise ValueError("duplicate PL/Plus entity: " + entity.name)
        self.entities[entity.id] = entity
        return entity

    def evidence(self, node, rule):
        return Evidence(
            source_range=self.mapping.range(node),
            analyzer="plplus",
            analyzer_version="1",
            rule=rule,
            description=_LIMITS,
        )

    def relation(self, origin, node, kind, resolution, coverage, tag=""):
        return self.add(
            Relation(
                **self.env(
                    EntityType.RELATION,
                    self.key(kind.value + tag, node),
                    kind.value,
                    node,
                ),
                relation_kind=kind,
                source=EntityRef(id=origin.id, entity_type=origin.entity_type),
                resolution=resolution,
                certainty=Certainty.STATIC_PROVEN
                if resolution.status == "RESOLVED"
                else Certainty.UNKNOWN,
                evidence=(self.evidence(node, kind.value),),
                coverage=coverage,
            )
        )

    def link(self, origin, target, node, kind, coverage):
        return self.relation(
            origin,
            node,
            kind,
            Resolution(
                status="RESOLVED",
                target=EntityRef(id=target.id, entity_type=target.entity_type),
            ),
            coverage,
            target.id,
        )

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
        if parent:
            self.link(
                parent.scope, scope, node, RelationKind.CONTAINS, capabilities()[1]
            )
        return _Frame(scope, parent, owner)

    def occurrence(self, node, frame, kind, target=None):
        entity = self.add(
            Occurrence(
                **self.env(
                    EntityType.OCCURRENCE,
                    self.key("occurrence:" + kind, node),
                    node.getText() or kind,
                    node,
                ),
                scope_id=frame.scope.id,
                occurrence_kind=kind,
                resolution="RESOLVED" if target else "UNRESOLVED",
                target_symbol_id=target.id if target else None,
            )
        )
        if target:
            self.link(
                entity,
                target,
                node,
                RelationKind.DECLARES
                if kind == "DECLARATION"
                else RelationKind.REFERENCES,
                capabilities()[1],
            )
        return entity

    def variable(self, node, name_node, frame, kind, type_name):
        name = _name(name_node.getText())
        symbol = self.add(
            Symbol(
                **self.env(
                    EntityType.SYMBOL, self.key(kind, name_node), name, name_node
                ),
                symbol_kind=kind,
                qualified_name=frame.owner.qualified_name + "." + name,
                scope_id=frame.scope.id,
                type_ref=TypeRef(name=type_name),
            )
        )
        frame.variables.setdefault(name, []).append((node, symbol))
        self.occurrence(name_node, frame, "DECLARATION", symbol)
        self.link(
            frame.scope, symbol, name_node, RelationKind.CONTAINS, capabilities()[1]
        )

    def declarations(self, node, frame):
        kind = _kind(node)
        if kind in _CALLABLES:
            name_node = node.identifier()
            name = _name(name_node.getText())
            params = node.parameterList().parameter() if node.parameterList() else []
            signature = CallableSignature(
                parameter_types=tuple(
                    TypeRef(name=_name(p.typeSpec().getText())) for p in params
                ),
                return_type=TypeRef(name=_name(node.typeSpec().getText()))
                if kind == "FunctionDeclaration"
                else None,
            )
            key = callable_key(frame.owner.logical_key, name, signature)
            symbol_id = logical_id(
                self.source.file.repository_id, EntityType.SYMBOL, key
            )
            symbol = self.entities.get(symbol_id)
            body = node.subprogramBody() is not None
            if body and symbol_id in self.body_ids:
                raise ValueError("duplicate subprogram body: " + name)
            if body:
                self.body_ids.add(symbol_id)
            if symbol is not None and symbol.signature != signature:
                raise ValueError("incompatible subprogram declarations: " + name)
            if symbol is None:
                symbol = self.add(
                    Symbol(
                        **self.env(EntityType.SYMBOL, key, name, name_node),
                        symbol_kind="METHOD",
                        qualified_name=frame.owner.qualified_name + "." + name,
                        scope_id=frame.scope.id,
                        owner_key=frame.owner.logical_key,
                        signature=signature,
                    )
                )
                self.link(
                    frame.scope,
                    symbol,
                    name_node,
                    RelationKind.CONTAINS,
                    capabilities()[1],
                )
            function = _Function(
                symbol, self.source.file.path, frame, frame is self.section_frame, body
            )
            self.functions.append(function)
            frame.functions.setdefault(name, []).append(function)
            self.occurrence(name_node, frame, "DECLARATION", symbol)
            frame = self.scope("CALLABLE", node, frame, symbol)
        elif kind in ("Block", "LoopStatement"):
            frame = self.scope("BLOCK", node, frame, frame.owner)
        self.frames[id(node)] = frame
        if kind in ("VariableDeclaration", "Parameter"):
            self.variable(
                node,
                node.identifier(),
                frame,
                "PARAMETER" if kind == "Parameter" else "LOCAL_VARIABLE",
                _name(node.typeSpec().getText()),
            )
        elif kind in ("NumericFor", "ObjectFor"):
            self.variable(
                node, node.identifier(), frame, "LOCAL_VARIABLE", "plplus.dynamic"
            )
        for child in _children(node):
            self.declarations(child, frame)

    def build(self):
        if not self.valid:
            return
        try:
            tree = self.parsed.tree
            root = self.scope("FILE", tree, None, None)
            label = (
                "cft::" + self.own_class
                if self.context
                else "<unit:" + self.source.file.path + ">"
            )
            owner = self.add(
                Symbol(
                    **self.env(
                        EntityType.SYMBOL, self.source.file.path + ":class", label
                    ),
                    symbol_kind="CLASS",
                    qualified_name=label,
                    scope_id=root.scope.id,
                )
            )
            frame = self.scope("TYPE", tree, root, owner)
            section_name = self.context[3] if self.context else "<section>"
            signature = CallableSignature()
            section = self.add(
                Symbol(
                    **self.env(
                        EntityType.SYMBOL,
                        callable_key(owner.logical_key, section_name, signature),
                        section_name,
                    ),
                    symbol_kind="METHOD",
                    qualified_name=label + "::" + section_name,
                    scope_id=frame.scope.id,
                    owner_key=owner.logical_key,
                    signature=signature,
                )
            )
            self.link(root.scope, owner, tree, RelationKind.CONTAINS, capabilities()[1])
            self.link(
                frame.scope, section, tree, RelationKind.CONTAINS, capabilities()[1]
            )
            self.section = section
            self.section_frame = self.scope("CALLABLE", tree, frame, section)
            self.declarations(tree, self.section_frame)
            for token in self.parsed.tokens:
                if token.type in (
                    self.parsed.tree.parser.MACRO,
                    self.parsed.tree.parser.PREPROC_ELSE,
                ) or (token.text or "").lower().lstrip().startswith("--#"):
                    self.diagnostics.append(
                        SourceDiagnostic(
                            severity="WARNING",
                            code="plplus.UNEXPANDED_PREPROCESSOR",
                            message="Macro/conditional compilation is not expanded",
                            source_range=self.mapping.range(token),
                        )
                    )
        except ValueError as error:
            self.valid = False
            self.entities.clear()
            self.diagnostics.append(
                SourceDiagnostic(
                    severity="ERROR", code="plplus.EXTRACTION_ERROR", message=str(error)
                )
            )

    def lookup(self, name, node, frame):
        while frame:
            candidates = [
                symbol
                for declaration, symbol in frame.variables.get(name, ())
                if symbol.symbol_kind == "PARAMETER"
                or declaration.stop.stop < node.start.start
            ]
            if candidates:
                return candidates[0] if len(candidates) == 1 else None
            frame = frame.parent
        return None

    def external(self, node, frame, selector, rule):
        ref = self.add(
            ExternalReference(
                **self.env(
                    EntityType.EXTERNAL_REFERENCE,
                    self.key("external:" + rule, node),
                    selector,
                    node,
                ),
                source=EntityRef(id=frame.owner.id, entity_type=EntityType.SYMBOL),
                selector=SymbolSelector(qualified_name=selector),
                reason=_LIMITS,
                evidence=(self.evidence(node, rule),),
                certainty=Certainty.UNKNOWN,
                coverage=capabilities()[3 if rule.startswith("cft.") else 2],
            )
        )
        self.link(
            frame.owner, ref, node, RelationKind.EXTERNAL_DEPENDENCY, ref.coverage
        )
        return ref

    def call(self, node, frame, catalog):
        prefix = node.namePrefix().getText()
        suffixes = node.nameSuffix()
        name = _name(prefix)
        candidates = []
        target = None
        if (
            prefix.startswith("::[")
            and suffixes
            and suffixes[0].getText().startswith(".[")
        ):
            target = (_bracket(prefix[2:]), _bracket(suffixes[0].getText()[1:]))
        elif (
            prefix.startswith("[")
            and suffixes
            and suffixes[0].getText().startswith("::[")
        ):
            target = (_bracket(prefix), _bracket(suffixes[0].getText()[2:]))
        if target:
            tail = suffixes[1].getText() if len(suffixes) > 1 else ""
            function_name = (
                _name(tail[1:])
                if tail.startswith(".") and tail[1:].isidentifier()
                else None
            )
            namespace = self.context[0] if self.context else None
            if namespace is not None:
                for unit in catalog:
                    if (
                        unit.valid
                        and unit.context
                        and unit.context[:2] == (namespace, target[0])
                        and unit.context[3] == target[1]
                    ):
                        candidates.extend(
                            [
                                f
                                for f in unit.functions
                                if f.top_level and f.symbol.name == function_name
                            ]
                            if function_name
                            else [
                                _Function(
                                    unit.section,
                                    unit.source.file.path,
                                    unit.section_frame,
                                    True,
                                    True,
                                )
                            ]
                        )
            selector = "cft.call::" + "::".join(
                (*target, *((function_name,) if function_name else ()))
            )
        else:
            short_call = all(s.LPAREN() is not None for s in suffixes)
            lexical = frame if short_call else None
            while lexical:
                if name in lexical.functions:
                    candidates = lexical.functions[name]
                    break
                if name in lexical.variables:
                    break
                lexical = lexical.parent
            if (
                short_call
                and not candidates
                and not self.lookup(name, node, frame)
                and self.context
            ):
                candidates = [
                    f
                    for unit in catalog
                    if unit.valid and unit.context == self.context
                    for f in unit.functions
                    if f.top_level and f.symbol.name == name
                ]
            selector = "plplus.call::" + node.getText()
        unique = {f.symbol.id: f for f in candidates}
        self.occurrence(node, frame, "CALL")
        if unique:
            self.dependencies.update(
                f.path for f in unique.values() if f.path != self.source.file.path
            )
            refs = tuple(
                EntityRef(id=f.symbol.id, entity_type=EntityType.SYMBOL)
                for f in sorted(unique.values(), key=lambda f: f.symbol.id)
            )
            self.relation(
                frame.owner,
                node,
                RelationKind.CALLS,
                Resolution(
                    status="PARTIAL" if len(refs) == 1 else "AMBIGUOUS",
                    candidates=refs,
                    reason=_LIMITS,
                ),
                capabilities()[2],
            )
        else:
            self.external(node, frame, selector, "plplus.call.unresolved")

    def query_aliases(self, node):
        """Only direct sources belong to this query; nested scopes are visited separately."""
        aliases = {}
        source = node.querySource() if hasattr(node, "querySource") else None
        if source:
            for item in source.sourceItem():
                reference = item.reference()
                if reference is None or reference.nameChain() is None:
                    identifiers = (
                        node.identifier() if hasattr(node, "identifier") else None
                    )
                    identifier = (
                        identifiers[-1]
                        if isinstance(identifiers, list) and identifiers
                        else identifiers
                    )
                    alias = item.identifier() or identifier
                    if alias is not None:
                        aliases.setdefault(_name(alias.getText()), []).append(None)
                    continue
                chain = reference.nameChain()
                prefix = chain.namePrefix().getText()
                cls = (
                    _bracket(prefix[2:])
                    if prefix.startswith("::[")
                    and all(s.LPAREN() is not None for s in chain.nameSuffix())
                    else None
                )
                identifiers = node.identifier() if hasattr(node, "identifier") else None
                identifier = (
                    identifiers[-1]
                    if isinstance(identifiers, list) and identifiers
                    else identifiers
                )
                alias = (
                    item.identifier().getText()
                    if item.identifier()
                    else identifier.getText()
                    if identifier is not None
                    else None
                )
                if alias:
                    aliases.setdefault(_name(alias), []).append(cls)
        if _kind(node) == "InsertStatement":
            chains = node.nameChain()
            chain = chains[-1] if chains else None
            if chain and node.identifier():
                prefix = chain.namePrefix().getText()
                identifiers = node.identifier()
                identifier = (
                    identifiers[-1] if isinstance(identifiers, list) else identifiers
                )
                aliases.setdefault(_name(identifier.getText()), []).append(
                    _bracket(prefix[2:])
                    if prefix.startswith("::[")
                    and all(s.LPAREN() is not None for s in chain.nameSuffix())
                    else None
                )
        return aliases

    def access(self, node, frame, cls, attr, mode, role):
        self.occurrence(node, frame, "READ" if mode == "READ" else "WRITE")
        selector = (
            "cft.attribute::" + (cls or "<unknown>") + "::" + attr
            if attr
            else "cft.class::" + cls
        )
        rule = "cft." + mode + (".ATTRIBUTE." + role if attr else ".CLASS")
        self.external(node, frame, selector, rule)

    def references(self, node, catalog, queries=()):
        frame = self.frames[id(node)]
        kind = _kind(node)
        if kind in _QUERIES:
            if (
                kind == "SelectQuery"
                and _kind(node.parentCtx) == "SelectQuery"
                and node.parentCtx.setOperator() is not None
            ):
                queries = queries[:-1]
            queries = (*queries, (node, self.query_aliases(node)))
        if kind == "NameChain":
            prefix = node.namePrefix()
            head = prefix.getText()
            suffixes = node.nameSuffix()
            called = any(s.LPAREN() is not None for s in suffixes)
            assignment = node.parentCtx
            write = (
                _kind(assignment) == "AssignmentOrCall"
                and assignment.ASSIGN() is not None
                and assignment.nameChain() is node
            )
            target_parent = (
                assignment.parentCtx if _kind(assignment) == "Reference" else assignment
            )
            if (
                _kind(target_parent) == "AssignmentOrCall"
                and target_parent.ASSIGN() is not None
                or _kind(target_parent) == "IntoClause"
            ):
                write = True
            elif _kind(assignment) == "FetchStatement":
                write = node in assignment.nameChain()[1:]
            elif _kind(assignment) == "ExecuteImmediateStatement":
                write = node in assignment.nameChain()
            source_item = node.parentCtx
            if _kind(source_item) == "Reference":
                source_item = source_item.parentCtx
            class_source = (
                head.startswith("::[")
                and all(s.LPAREN() is not None for s in suffixes)
                and _kind(source_item) in ("SourceItem", "InsertStatement")
            )
            if _kind(assignment) == "AssignmentOrCall" and assignment.ASSIGN() is None:
                called = True
            if class_source:
                called = False
            if called:
                self.call(node, frame, catalog)
            elif not suffixes and not head.startswith(("::", "[")):
                symbol = self.lookup(_name(head), node, frame)
                self.occurrence(prefix, frame, "WRITE" if write else "READ", symbol)
            if not called and head.startswith("::["):
                mode = "READ"
                if queries:
                    query = queries[-1][0]
                    if _kind(source_item) == "SourceItem" or (
                        _kind(query) == "InsertStatement"
                        and node.parentCtx is query
                        and node is query.nameChain()[-1]
                    ):
                        mode = _QUERIES[_kind(query)]
                self.access(prefix, frame, _bracket(head[2:]), None, mode, "source")
            attr_node = None
            cls = None
            if head.startswith("[") and not (
                suffixes and suffixes[0].getText().startswith("::")
            ):
                attr_node = prefix
                cls = self.own_class
            elif (
                not head.startswith("::")
                and suffixes
                and suffixes[0].getText().startswith(".[")
            ):
                attr_node = suffixes[0]
                for query, aliases in reversed(queries):
                    if _name(head) in aliases:
                        values = aliases[_name(head)]
                        cls = values[0] if len(values) == 1 else None
                        break
            if attr_node is not None:
                if attr_node is prefix:
                    ancestor = node.parentCtx
                    while ancestor is not None and _kind(ancestor) not in (
                        *_QUERIES,
                        "NameChain",
                    ):
                        ancestor = ancestor.parentCtx
                    if _kind(ancestor) == "NameChain":
                        constructor_head = ancestor.namePrefix().getText()
                        if constructor_head.startswith("::[") and all(
                            s.LPAREN() is not None for s in ancestor.nameSuffix()
                        ):
                            cls = _bracket(constructor_head[2:])
                attr = _bracket(attr_node.getText().removeprefix(".")) or "<unknown>"
                role = (
                    "into"
                    if write and _kind(target_parent) == "IntoClause"
                    else "write"
                    if write
                    else "select"
                )
                parent, child = node.parentCtx, node
                while parent is not None and _kind(parent) not in _QUERIES:
                    pk = _kind(parent)
                    if pk == "SetItem":
                        write = parent.reference() is child
                        role = (
                            "into"
                            if write and _kind(target_parent) == "IntoClause"
                            else "write"
                            if write
                            else "select"
                        )
                        break
                    if pk in (
                        "WhereClause",
                        "HavingClause",
                        "GroupByClause",
                        "OrderByClause",
                    ):
                        role = {
                            "WhereClause": "where",
                            "HavingClause": "having",
                            "GroupByClause": "group",
                            "OrderByClause": "order",
                        }[pk]
                        break
                    parent, child = parent.parentCtx, parent
                self.access(
                    attr_node, frame, cls, attr, "WRITE" if write else "READ", role
                )
        for child in _children(node):
            self.references(child, catalog, queries)

    def result(self):
        return AdapterFileResult(
            analysis=FileAnalysis(
                path=self.source.file.path,
                entities=tuple(self.entities.values()) if self.valid else (),
                dependencies=tuple(sorted(self.dependencies)),
            ),
            diagnostics=tuple(self.diagnostics),
            capabilities=capabilities(not self.valid),
        )


def build_plplus(
    sources: tuple[SourceInput, ...],
) -> tuple[str, dict[str, AdapterFileResult]]:
    """Build a captured-source catalog and immutable per-file adapter results."""
    units = [
        _Unit(source, parse_plplus(source))
        for source in sorted(sources, key=lambda s: s.file.path)
    ]
    for unit in units:
        unit.build()
    definitions = [
        (
            u.source.file.path,
            u.valid,
            [(f.symbol.id, f.symbol.model_dump(mode="json")) for f in u.functions],
        )
        for u in units
    ]
    version = (
        "plplus/1:antlr/4.13.2:catalog/"
        + hashlib.sha256(
            json.dumps(definitions, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )
    for unit in units:
        if unit.valid:
            unit.references(unit.parsed.tree, units)
    return version, {u.source.file.path: u.result() for u in units}
