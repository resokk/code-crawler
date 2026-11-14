"""Conservative Java lexical symbols/occurrences adapter over the existing AST."""

import asyncio
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field

from tree_sitter import Node

from code_crawler import java
from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.ucm import (
    CallableSignature,
    Certainty,
    Coverage,
    Entity,
    EntityRef,
    EntityType,
    Evidence,
    Occurrence,
    Relation,
    RelationKind,
    Resolution,
    Scope,
    SourceRange,
    Symbol,
    TypeRef,
    callable_key,
    logical_id,
)

_LIMITS = (
    "syntax-only types; imports, bounds and classpath are not resolved",
    "call applicability and unsupported Java constructs are not analyzed",
)
_EXCLUDED = {
    "lambda_expression",
    "catch_clause",
    "enhanced_for_statement",
    "try_with_resources_statement",
    "switch_expression",
    "switch_statement",
    "method_reference",
    "enum_constant",
    "compact_constructor_declaration",
    "annotation_type_element_declaration",
}


@dataclass(frozen=True)
class JavaSymbolsResult:
    analysis: FileAnalysis
    diagnostics: tuple[java.Diagnostic, ...]
    coverage: Coverage
    _extractor: "_Extractor | None" = field(default=None, repr=False, compare=False)


def _name(node: Node | None, erase: bool = False) -> str:
    if node is None:
        return ""
    if node.type == "array_type":
        return _name(node.child_by_field_name("element"), erase) + _dimensions(
            node.child_by_field_name("dimensions")
        )
    if node.type == "generic_type" and erase:
        return _name(node.named_children[0], erase)
    if node.type == "scoped_type_identifier":
        return ".".join(_name(child, erase) for child in node.named_children)
    return re.sub(r"\s+", "", java._text(node))


def _dimensions(node: Node | None) -> str:
    return "[]" * sum(child.type == "[" for child in node.children) if node else ""


def _parameter(node: Node, erase: bool = False) -> tuple[Node | None, str]:
    if node.type == "spread_parameter":
        declarator = next(
            (c for c in node.named_children if c.type == "variable_declarator"), None
        )
        type_node = next(
            (
                c
                for c in node.named_children
                if c.type not in ("modifiers", "variable_declarator")
            ),
            None,
        )
        return declarator.child_by_field_name("name") if declarator else None, _name(
            type_node, erase
        ) + "[]"
    return node.child_by_field_name("name"), _name(
        node.child_by_field_name("type"), erase
    ) + _dimensions(node.child_by_field_name("dimensions"))


def _has_patterns(node: Node) -> bool:
    pending = [node]
    while pending:
        current = pending.pop()
        if current.type.endswith("_pattern") or (
            current.type == "instanceof_expression"
            and current.child_by_field_name("name") is not None
        ):
            return True
        pending.extend(current.named_children)
    return False


class _Extractor:
    def __init__(self, source: SourceInput, parsed: java.ParseResult) -> None:
        self.source = source
        self.repo = source.file.repository_id
        self.parsed = parsed
        self.entities: list[Entity] = []
        self.scopes: dict[str, Scope] = {}
        self.bindings: dict[str, list[tuple[Symbol, int]]] = defaultdict(list)
        self.declarations: dict[int, tuple[Symbol, str]] = {}
        self.nodes: list[tuple[Node, str]] = []
        self.symbol_nodes: dict[str, Node] = {}
        self.parameters: set[int] = set()
        self.keys: set[str] = set()
        self.blocks: dict[str, int] = defaultdict(int)
        self.coverage = Coverage(
            capability="java.symbols",
            analyzer_version="1",
            status="PARTIAL",
            reasons=(
                *_LIMITS,
                *(("parser diagnostics present",) if parsed.diagnostics else ()),
            ),
        )

    def range(self, node: Node) -> SourceRange:
        span = java._span(node)
        return SourceRange(
            source_file_id=self.source.file.id, start=span.start, end=span.end
        )

    def scope(
        self, key: str, kind: str, parent: str | None, owner: str | None, node: Node
    ) -> Scope:
        scope = Scope(
            repository_id=self.repo,
            logical_key=key,
            id=logical_id(self.repo, EntityType.SCOPE, key),
            name=kind,
            scope_kind=kind,
            parent_scope_id=parent,
            owner_symbol_id=owner,
            source_range=self.range(node),
        )
        if scope.id in self.scopes:
            raise ValueError("duplicate Java scope identity")
        self.scopes[scope.id] = scope
        self.entities.append(scope)
        return scope

    def declare(
        self,
        key: str,
        kind: str,
        name: str,
        qualified: str,
        scope: str,
        name_node: Node,
        declaration: Node,
        **fields: object,
    ) -> Symbol:
        if key in self.keys:
            raise ValueError("duplicate Java declaration identity")
        self.keys.add(key)
        symbol = Symbol(
            repository_id=self.repo,
            logical_key=key,
            id=logical_id(self.repo, EntityType.SYMBOL, key),
            name=name,
            qualified_name=qualified,
            symbol_kind=kind,
            scope_id=scope,
            source_range=self.range(declaration),
            **fields,
        )
        self.entities.append(symbol)
        self.symbol_nodes[symbol.id] = declaration
        self.declarations[name_node.id] = (symbol, scope)
        visible = name_node.end_byte if kind == "LOCAL_VARIABLE" else -1
        self.bindings[scope].append((symbol, visible))
        return symbol

    def walk(self, node: Node, scope: str, owner: Symbol | None, package: str) -> None:
        if node.type in _EXCLUDED or node.type in (
            "package_declaration",
            "import_declaration",
            "modifiers",
        ):
            return
        if node.type == "object_creation_expression" and any(
            c.type == "class_body" for c in node.named_children
        ):
            return
        if node.type in java._TYPES:
            name_node = node.child_by_field_name("name")
            if name_node is None or name_node.is_missing:
                return
            name = java._text(name_node)
            qualified = f"{owner.qualified_name if owner else package}.{name}".lstrip(
                "."
            )
            key = "java:type:" + qualified
            if self.scopes[scope].scope_kind not in ("FILE", "TYPE"):
                key = json.dumps(
                    ["java:local-type", self.scopes[scope].logical_key, name],
                    separators=(",", ":"),
                )
            symbol = self.declare(key, "CLASS", name, qualified, scope, name_node, node)
            nested = self.scope(
                "java:type-scope:" + key, "TYPE", scope, symbol.id, node
            )
            for child in node.named_children:
                self.walk(child, nested.id, symbol, package)
            return
        if node.type in ("method_declaration", "constructor_declaration"):
            if owner is None:
                return
            name_node = node.child_by_field_name("name")
            if name_node is None or name_node.is_missing:
                return
            params_node = node.child_by_field_name("parameters")
            if params_node is not None and params_node.has_error:
                return
            params = (
                [
                    c
                    for c in params_node.named_children
                    if c.type in ("formal_parameter", "spread_parameter")
                ]
                if params_node
                else []
            )
            if any(
                _parameter(p)[0] is None or not _parameter(p, True)[1] for p in params
            ):
                return
            constructor = node.type == "constructor_declaration"
            name = "<init>" if constructor else java._text(name_node)
            returns = _name(node.child_by_field_name("type")) + _dimensions(
                node.child_by_field_name("dimensions")
            )
            signature = CallableSignature(
                parameter_types=tuple(
                    TypeRef(name=_parameter(p, True)[1]) for p in params
                ),
                return_type=TypeRef(name=returns)
                if returns and not constructor
                else None,
            )
            key = callable_key(owner.logical_key, name, signature)
            symbol = self.declare(
                key,
                "CONSTRUCTOR" if constructor else "METHOD",
                name,
                owner.qualified_name + "." + name,
                scope,
                name_node,
                node,
                owner_key=owner.logical_key,
                signature=signature,
            )
            nested = self.scope(
                "java:callable-scope:" + key, "CALLABLE", scope, symbol.id, node
            )
            for ordinal, param in enumerate(params):
                self.parameters.add(param.id)
                param_name, type_name = _parameter(param)
                self.declare(
                    key + f":parameter:{ordinal}",
                    "PARAMETER",
                    java._text(param_name),
                    symbol.qualified_name + "." + java._text(param_name),
                    nested.id,
                    param_name,
                    param,
                    type_ref=TypeRef(name=type_name),
                )
            for child in node.named_children:
                if child == node.child_by_field_name("body") and _has_patterns(child):
                    continue
                self.walk(child, nested.id, owner, package)
            return
        if (
            node.type in ("formal_parameter", "spread_parameter")
            and node.id not in self.parameters
        ):
            return
        if node.type in ("block", "constructor_body", "for_statement"):
            ordinal = self.blocks[scope]
            self.blocks[scope] += 1
            scope = self.scope(
                self.scopes[scope].logical_key + f":block:{ordinal}",
                "BLOCK",
                scope,
                None,
                node,
            ).id
        if node.type in (
            "field_declaration",
            "constant_declaration",
            "local_variable_declaration",
        ):
            kind = (
                "FIELD"
                if node.type != "local_variable_declaration"
                else "LOCAL_VARIABLE"
            )
            type_name = _name(node.child_by_field_name("type"))
            for declaration in node.children_by_field_name("declarator"):
                name_node = declaration.child_by_field_name("name")
                if name_node is None or name_node.is_missing:
                    continue
                name = java._text(name_node)
                key = (
                    (
                        owner.logical_key
                        if kind == "FIELD" and owner
                        else self.scopes[scope].logical_key
                    )
                    + ":"
                    + kind
                    + ":"
                    + name
                )
                self.declare(
                    key,
                    kind,
                    name,
                    (owner.qualified_name + "." if owner else "") + name,
                    scope,
                    name_node,
                    declaration,
                    type_ref=TypeRef(
                        name=type_name
                        + _dimensions(declaration.child_by_field_name("dimensions"))
                    )
                    if type_name
                    else None,
                )
        if node.type in ("identifier", "type_identifier") and not node.is_missing:
            self.nodes.append((node, scope))
        for child in node.named_children:
            if (
                node.type == "variable_declarator"
                and child == node.child_by_field_name("value")
                and _has_patterns(child)
            ):
                continue
            self.walk(child, scope, owner, package)

    def lookup(
        self,
        name: str,
        scope: str,
        offset: int,
        kinds: set[str],
        this_field: bool = False,
    ) -> list[Symbol]:
        current = self.scopes[scope]
        while True:
            if not this_field or current.scope_kind == "TYPE":
                found = [
                    s
                    for s, visible in self.bindings[current.id]
                    if s.name == name and s.symbol_kind in kinds and visible <= offset
                ]
                if found or this_field:
                    return found
            if current.parent_scope_id is None:
                return []
            current = self.scopes[current.parent_scope_id]

    def occurrences(self) -> None:
        for node, scope in self.nodes:
            declaration = self.declarations.get(node.id)
            name = java._text(node)
            kinds = ["REFERENCE"] if node.type == "type_identifier" else ["READ"]
            candidates = []
            if declaration:
                candidates = [declaration[0]]
                scope = declaration[1]
                kinds = ["DECLARATION"]
            elif node.parent.type in (
                "break_statement",
                "continue_statement",
                "labeled_statement",
            ):
                continue
            elif (
                node.parent.type == "method_invocation"
                and node.parent.child_by_field_name("name") == node
            ):
                kinds = ["CALL"]
                receiver = node.parent.child_by_field_name("object")
                if receiver is None or receiver.type == "this":
                    candidates = self.lookup(name, scope, node.start_byte, {"METHOD"})
            elif node.type != "type_identifier":
                target = node
                field = (
                    node.parent.type == "field_access"
                    and node.parent.child_by_field_name("field") == node
                )
                if field:
                    target = node.parent
                    receiver = target.child_by_field_name("object")
                    if receiver is not None and receiver.type == "this":
                        candidates = self.lookup(
                            name, scope, node.start_byte, {"FIELD"}, this_field=True
                        )
                else:
                    candidates = self.lookup(
                        name,
                        scope,
                        node.start_byte,
                        {"FIELD", "LOCAL_VARIABLE", "PARAMETER"},
                    )
                parent = target.parent
                if (
                    parent
                    and parent.type == "assignment_expression"
                    and parent.child_by_field_name("left") == target
                ):
                    operator = java._text(parent.child_by_field_name("operator"))
                    kinds = ["WRITE"] if operator == "=" else ["READ", "WRITE"]
                elif parent and parent.type == "update_expression":
                    kinds = ["READ", "WRITE"]
            for kind in kinds:
                resolved = len(candidates) == 1 and kind != "CALL"
                status = (
                    "RESOLVED"
                    if resolved
                    else "AMBIGUOUS"
                    if len(candidates) > 1
                    else "UNRESOLVED"
                )
                key = json.dumps(
                    [
                        "java:occurrence",
                        self.source.file.path,
                        node.start_byte,
                        node.end_byte,
                        kind,
                    ],
                    separators=(",", ":"),
                )
                occurrence = Occurrence(
                    repository_id=self.repo,
                    logical_key=key,
                    id=logical_id(self.repo, EntityType.OCCURRENCE, key),
                    name=name,
                    occurrence_kind=kind,
                    scope_id=scope,
                    source_range=self.range(node),
                    resolution=status,
                    target_symbol_id=candidates[0].id if resolved else None,
                )
                self.entities.append(occurrence)
                relation_key = key + ":relation"
                relation_resolution = (
                    Resolution(
                        status="RESOLVED",
                        target=EntityRef(
                            id=candidates[0].id, entity_type=EntityType.SYMBOL
                        ),
                    )
                    if resolved
                    else Resolution(
                        status=status,
                        candidates=tuple(
                            EntityRef(id=s.id, entity_type=EntityType.SYMBOL)
                            for s in candidates
                        )
                        if status == "AMBIGUOUS"
                        else (),
                        reason="lexical collector does not prove target applicability",
                    )
                )
                self.entities.append(
                    Relation(
                        repository_id=self.repo,
                        logical_key=relation_key,
                        id=logical_id(self.repo, EntityType.RELATION, relation_key),
                        name=kind,
                        relation_kind=RelationKind.DECLARES
                        if declaration
                        else RelationKind.REFERENCES,
                        source=EntityRef(
                            id=occurrence.id, entity_type=EntityType.OCCURRENCE
                        ),
                        resolution=relation_resolution,
                        certainty=Certainty.STATIC_PROVEN
                        if declaration
                        else Certainty.INFERRED
                        if resolved
                        else Certainty.UNKNOWN,
                        evidence=(
                            Evidence(
                                source_range=self.range(node),
                                analyzer="java.symbols",
                                analyzer_version="1",
                                rule="ast.declaration"
                                if declaration
                                else "ast.lexical-reference",
                                description="Java lexical syntax; no execution inference",
                            ),
                        ),
                        coverage=self.coverage,
                    )
                )


def extract(source: SourceInput) -> JavaSymbolsResult:
    """Extract conservative UCM declarations/occurrences from captured Java bytes."""
    if source.file.language != "java":
        raise ValueError("Java adapter requires language=java")
    parsed = java.analyze(source.content)
    if parsed.source_sha256 != source.file.content_sha256:
        raise ValueError("source fingerprint does not match captured bytes")
    extractor = _Extractor(source, parsed)
    if parsed._tree is not None:
        root = parsed._tree.root_node
        package = next(
            (
                java._text(child.named_children[-1])
                for child in root.named_children
                if child.type == "package_declaration"
            ),
            "",
        )
        scope = extractor.scope(
            "java:file-scope:" + source.file.path, "FILE", None, None, root
        )
        extractor.walk(root, scope.id, None, package)
        extractor.occurrences()
    return JavaSymbolsResult(
        FileAnalysis(path=source.file.path, entities=tuple(extractor.entities)),
        parsed.diagnostics,
        extractor.coverage,
        extractor,
    )


async def analyze_files(sources: tuple[SourceInput, ...]) -> tuple[FileAnalysis, ...]:
    """Incremental callback for Java files; caller owns publication and analysis version."""

    def analyze() -> tuple[FileAnalysis, ...]:
        results = [extract(source) for source in sources]
        failures = [result.analysis.path for result in results if result.diagnostics]
        if failures:
            raise ValueError(
                "Java parser diagnostics prevent canonical indexing: "
                + ", ".join(failures)
            )
        return tuple(result.analysis for result in results)

    return await asyncio.to_thread(analyze)
