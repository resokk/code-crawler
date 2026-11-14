"""Conservative repository-local declared-method call resolution."""

import asyncio
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

import asyncpg
from tree_sitter import Node

from code_crawler import java
from code_crawler.incremental import (
    FileAnalysis,
    IncrementalResult,
    SourceInput,
    _capture,
    index_incremental,
    tick,
)
from code_crawler.java_symbols import JavaSymbolsResult, extract
from code_crawler.ucm import (
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
    Symbol,
    SymbolSelector,
    logical_id,
)

_PRIMITIVES = {"byte", "short", "char", "int", "long", "float", "double", "boolean"}
_WIDEN = {
    "byte": ["short", "int", "long", "float", "double"],
    "short": ["int", "long", "float", "double"],
    "char": ["int", "long", "float", "double"],
    "int": ["long", "float", "double"],
    "long": ["float", "double"],
    "float": ["double"],
}
_JAVA_LANG = {
    "String",
    "StringBuilder",
    "StringBuffer",
    "Object",
    "Integer",
    "Long",
    "Double",
    "Float",
    "Short",
    "Byte",
    "Character",
    "Boolean",
    "Number",
}


def _erase(name: str) -> str:
    result = []
    depth = 0
    for char in name:
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif depth == 0 and not char.isspace():
            result.append(char)
    return "".join(result).replace("...", "[]")


def _modifiers(node: Node) -> set[str]:
    modifiers = next(
        (child for child in node.named_children if child.type == "modifiers"), None
    )
    return {child.type for child in modifiers.children} if modifiers else set()


def _type_variables(node: Node) -> set[str]:
    parameters = node.child_by_field_name("type_parameters")
    return (
        {
            java._text(p.named_children[0])
            for p in parameters.named_children
            if p.named_children
        }
        if parameters
        else set()
    )


@dataclass
class _File:
    source: SourceInput
    result: JavaSymbolsResult
    package: str
    imports: dict[str, list[str]]
    wildcard: bool
    static_imports: dict[str, list[str]]


@dataclass
class _Class:
    symbol: Symbol
    file: _File
    node: Node
    inherits: bool


@dataclass
class _Method:
    symbol: Symbol
    owner: _Class
    node: Node
    modifiers: set[str]
    varargs: bool


@dataclass
class _Site:
    file: _File
    node: Node
    occurrence: Occurrence
    caller: _Method


@dataclass
class _Result:
    target: _Method | None
    candidates: list[_Method]
    status: str
    reason: str
    selector: str
    external: bool


class JavaCallAnalyzer:
    """Closed-source method catalog and incremental callback with an explicit profile."""

    def __init__(self, sources: tuple[SourceInput, ...]) -> None:
        if len({s.file.repository_id for s in sources}) > 1 or len(
            {s.file.path for s in sources}
        ) != len(sources):
            raise ValueError(
                "Java catalog must contain unique files from one repository"
            )
        self.files: dict[str, _File] = {}
        self.classes: dict[str, _Class] = {}
        self.class_keys: dict[str, _Class] = {}
        self.methods: dict[str, _Method] = {}
        self.named: dict[tuple[str, str], list[_Method]] = defaultdict(list)
        self.sites: dict[tuple[str, int], _Site] = {}
        self.memo: dict[tuple[str, int], _Result] = {}
        self.coverage = Coverage(
            capability="java.calls",
            analyzer_version="1",
            status="PARTIAL",
            reasons=(
                "closed source catalog; classpath, inheritance and runtime dispatch are not modeled",
                "boxing, generic inference, varargs expansion and complex reference conversions are incomplete",
            ),
        )
        for source in sources:
            result = extract(source)
            if result.diagnostics:
                raise ValueError(
                    "Java parser diagnostics prevent canonical call resolution: "
                    + source.file.path
                )
            root = result._extractor.parsed._tree.root_node
            package = next(
                (
                    java._text(c.named_children[-1])
                    for c in root.named_children
                    if c.type == "package_declaration"
                ),
                "",
            )
            imports = defaultdict(list)
            static_imports = defaultdict(list)
            wildcard = False
            for child in root.named_children:
                if child.type == "import_declaration":
                    text = java._text(child)
                    if re.match(r"import\s+static\b", text):
                        match = re.fullmatch(r"import\s+static\s+([\w.$]+)\s*;", text)
                        if match:
                            static_imports[match[1].rsplit(".", 1)[-1]].append(match[1])
                        continue
                    match = re.fullmatch(r"import\s+([\w.$]+)\s*;", text)
                    if match:
                        imports[match[1].rsplit(".", 1)[-1]].append(match[1])
                    elif "*" in text:
                        wildcard = True
            file = _File(
                source, result, package, dict(imports), wildcard, dict(static_imports)
            )
            self.files[source.file.path] = file
            tick("Java: каталог", len(sources))
            extractor = result._extractor
            for entity in result.analysis.entities:
                if isinstance(entity, Symbol) and entity.symbol_kind == "CLASS":
                    global_type = entity.logical_key.startswith("java:type:")
                    if global_type and entity.qualified_name in self.classes:
                        raise ValueError("duplicate Java type in repository catalog")
                    node = extractor.symbol_nodes[entity.id]
                    inherits = (
                        node.child_by_field_name("superclass") is not None
                        or node.child_by_field_name("interfaces") is not None
                        or any(
                            c.type in ("extends_interfaces", "super_interfaces")
                            for c in node.named_children
                        )
                    )
                    info = _Class(entity, file, node, inherits)
                    if global_type:
                        self.classes[entity.qualified_name] = info
                    self.class_keys[entity.logical_key] = info
        for file in self.files.values():
            extractor = file.result._extractor
            symbols = {
                e.id: e for e in file.result.analysis.entities if isinstance(e, Symbol)
            }
            for symbol in symbols.values():
                if symbol.symbol_kind not in ("METHOD", "CONSTRUCTOR"):
                    continue
                node = extractor.symbol_nodes[symbol.id]
                params = node.child_by_field_name("parameters")
                varargs = params is not None and any(
                    p.type == "spread_parameter" for p in params.named_children
                )
                method = _Method(
                    symbol,
                    self.class_keys[symbol.owner_key],
                    node,
                    _modifiers(node),
                    varargs,
                )
                self.methods[symbol.id] = method
                if symbol.symbol_kind == "METHOD":
                    self.named[(method.owner.symbol.id, symbol.name)].append(method)
            occurrences = {
                (e.source_range.start.line, e.source_range.start.byte_column): e
                for e in file.result.analysis.entities
                if isinstance(e, Occurrence) and e.occurrence_kind == "CALL"
            }
            for node, scope_id in extractor.nodes:
                if (
                    node.parent.type != "method_invocation"
                    or node.parent.child_by_field_name("name") != node
                ):
                    continue
                occurrence = occurrences.get(
                    (node.start_point.row + 1, node.start_point.column)
                )
                if occurrence is None:
                    continue
                scope = extractor.scopes[scope_id]
                caller = None
                while True:
                    if scope.owner_symbol_id in self.methods:
                        caller = self.methods[scope.owner_symbol_id]
                        break
                    if scope.parent_scope_id is None:
                        break
                    scope = extractor.scopes[scope.parent_scope_id]
                if caller:
                    self.sites[(file.source.file.path, node.start_byte)] = _Site(
                        file, node.parent, occurrence, caller
                    )
        catalog = [
            (
                c.symbol.qualified_name,
                c.file.source.file.path,
                c.file.package,
                sorted(c.file.imports.items()),
                sorted(c.file.static_imports.items()),
                c.file.wildcard,
                c.inherits,
                sorted(_modifiers(c.node)),
            )
            for c in self.classes.values()
        ]
        signatures = [
            (
                m.symbol.id,
                m.symbol.signature.model_dump(mode="json"),
                sorted(m.modifiers),
                m.varargs,
            )
            for m in self.methods.values()
        ]
        digest = hashlib.sha256(
            json.dumps(
                [sorted(catalog), sorted(signatures)],
                sort_keys=True,
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        self.analysis_version = "java.calls/1:" + digest

    def qualify(self, name: str, file: _File, owner: _Class) -> str | None:
        name = _erase(name)
        if name.split("[", 1)[0].split(".", 1)[0] in _type_variables(owner.node):
            return None
        if name.endswith("[]"):
            element = self.qualify(name[:-2], file, owner)
            return element + "[]" if element else None
        if name in _PRIMITIVES or name == "void":
            return name
        prefix = owner.symbol.qualified_name
        while prefix:
            candidate = prefix + "." + name
            if candidate in self.classes:
                return candidate
            prefix = prefix.rsplit(".", 1)[0] if "." in prefix else ""
        if name == owner.symbol.name:
            return owner.symbol.qualified_name
        first, *rest = name.split(".")
        imported = file.imports.get(first, [])
        if len(imported) > 1:
            return None
        if imported:
            return ".".join([imported[0], *rest])
        static_imported = file.static_imports.get(first, [])
        if static_imported:
            if len(static_imported) == 1 and static_imported[0] in self.classes:
                return ".".join([static_imported[0], *rest])
            return None
        local = (file.package + "." if file.package else "") + name
        if local in self.classes:
            return local
        if name in self.classes or "." in name:
            return name
        if file.wildcard:
            return None
        if name in _JAVA_LANG:
            return "java.lang." + name
        return local if name != "var" else None

    def data_symbol(self, node: Node, site: _Site) -> Symbol | None:
        extractor = site.file.result._extractor
        if node.type == "identifier":
            matches = extractor.lookup(
                java._text(node),
                site.occurrence.scope_id,
                node.start_byte,
                {"FIELD", "LOCAL_VARIABLE", "PARAMETER"},
            )
        elif (
            node.type == "field_access"
            and node.child_by_field_name("object").type == "this"
        ):
            matches = extractor.lookup(
                java._text(node.child_by_field_name("field")),
                site.occurrence.scope_id,
                node.start_byte,
                {"FIELD"},
                this_field=True,
            )
        else:
            return None
        return matches[0] if len(matches) == 1 else None

    def local_type_shadow(self, name: str, site: _Site) -> bool:
        first = _erase(name).split("[", 1)[0].split(".", 1)[0]
        matches = site.file.result._extractor.lookup(
            first, site.occurrence.scope_id, site.node.start_byte, {"CLASS"}
        )
        return any(
            not symbol.logical_key.startswith("java:type:") for symbol in matches
        )

    def argument_type(self, node: Node, site: _Site) -> str | None:
        if node.type in (
            "decimal_integer_literal",
            "hex_integer_literal",
            "octal_integer_literal",
            "binary_integer_literal",
        ):
            return "long" if java._text(node).lower().endswith("l") else "int"
        if node.type in (
            "decimal_floating_point_literal",
            "hex_floating_point_literal",
        ):
            return "float" if java._text(node).lower().endswith("f") else "double"
        if node.type in ("true", "false", "boolean_literal"):
            return "boolean"
        if node.type == "string_literal":
            return "java.lang.String"
        if node.type == "character_literal":
            return "char"
        if node.type == "null_literal":
            return "null"
        if node.type == "this":
            return site.caller.owner.symbol.qualified_name
        if node.type == "parenthesized_expression":
            return self.argument_type(node.named_children[0], site)
        if node.type in ("cast_expression", "object_creation_expression"):
            type_node = node.child_by_field_name("type")
            return (
                self.qualify(java._text(type_node), site.file, site.caller.owner)
                if type_node
                else None
            )
        if node.type == "method_invocation":
            name = node.child_by_field_name("name")
            nested = (
                self.sites.get((site.file.source.file.path, name.start_byte))
                if name
                else None
            )
            result = self.resolve(nested) if nested else None
            if result and result.target and result.target.symbol.signature.return_type:
                target = result.target
                return self.qualify(
                    target.symbol.signature.return_type.name,
                    target.owner.file,
                    target.owner,
                )
            return None
        symbol = self.data_symbol(node, site)
        if (
            symbol
            and symbol.type_ref
            and self.local_type_shadow(symbol.type_ref.name, site)
        ):
            return None
        if (
            symbol
            and symbol.type_ref
            and _erase(symbol.type_ref.name).split("[", 1)[0].split(".", 1)[0]
            in _type_variables(site.caller.node)
        ):
            return None
        return (
            self.qualify(symbol.type_ref.name, site.file, site.caller.owner)
            if symbol and symbol.type_ref
            else None
        )

    def receiver(self, site: _Site) -> tuple[str | None, bool]:
        node = site.node.child_by_field_name("object")
        if node is None:
            return site.caller.owner.symbol.qualified_name, False
        if node.type == "this" and "static" in site.caller.modifiers:
            return None, False
        descriptor = self.argument_type(node, site)
        if descriptor:
            return descriptor, False
        if self.data_symbol(node, site) is not None:
            return None, False
        text = java._text(node)
        first = text.split(".")[0]
        if self.local_type_shadow(first, site):
            return None, False
        matches = site.file.result._extractor.lookup(
            first,
            site.occurrence.scope_id,
            node.start_byte,
            {"FIELD", "LOCAL_VARIABLE", "PARAMETER"},
        )
        if not matches and re.fullmatch(r"[\w$]+(?:\.[\w$]+)*", text):
            return self.qualify(text, site.file, site.caller.owner), True
        return None, False

    def conversion(
        self, actual: str | None, formal: str | None
    ) -> int | None | Literal[False]:
        if actual is None or formal is None:
            return None
        if actual == formal:
            return 0
        if actual == "null":
            return False if formal in _PRIMITIVES else 0
        if actual in _PRIMITIVES and formal in _PRIMITIVES:
            widening = _WIDEN.get(actual, [])
            return widening.index(formal) + 1 if formal in widening else False
        if actual in _PRIMITIVES or formal in _PRIMITIVES:
            if "java.lang.String" in (actual, formal):
                return False
            return None
        if formal == "java.lang.Object":
            return 1
        known = self.classes.get(actual)
        if known and not known.inherits and formal in self.classes:
            return False
        if actual == "java.lang.String" and formal in self.classes:
            return False
        return None

    def resolve(self, site: _Site) -> _Result:
        key = (
            site.file.source.file.path,
            site.node.child_by_field_name("name").start_byte,
        )
        if key in self.memo:
            return self.memo[key]
        receiver, is_class = self.receiver(site)
        name = site.occurrence.name
        selector = (
            (
                receiver
                or java._text(site.node.child_by_field_name("object"))
                or site.caller.owner.symbol.qualified_name
            )
            + "."
            + name
        )
        owner = self.classes.get(receiver)
        if receiver == site.caller.owner.symbol.qualified_name:
            owner = site.caller.owner
        declared = self.named.get((owner.symbol.id, name), []) if owner else []
        if not declared and site.node.child_by_field_name("object") is None:
            imported = site.file.static_imports.get(name, [])
            if len(imported) == 1:
                selector = imported[0]
                receiver = imported[0].rsplit(".", 1)[0]
                owner = self.classes.get(receiver)
                is_class = True
                declared = self.named.get((owner.symbol.id, name), []) if owner else []
        possible = []
        ranks = []
        args = site.node.child_by_field_name("arguments")
        actual = (
            [self.argument_type(arg, site) for arg in args.named_children]
            if args
            else []
        )
        for method in declared:
            if (
                method.owner.file.package != site.file.package
                and "public" not in _modifiers(method.owner.node)
            ):
                continue
            if is_class and "static" not in method.modifiers:
                continue
            if (
                site.node.child_by_field_name("object") is None
                and "static" in site.caller.modifiers
                and "static" not in method.modifiers
            ):
                continue
            if method.owner.symbol.id != site.caller.owner.symbol.id:
                if "private" in method.modifiers:
                    continue
                if (
                    method.owner.file.package != site.file.package
                    and "public" not in method.modifiers
                    and method.owner.node.type != "interface_declaration"
                ):
                    continue
            parameters = method.symbol.signature.parameter_types
            if len(parameters) != len(actual):
                if method.varargs and len(actual) >= len(parameters) - 1:
                    possible.append(method)
                    ranks.append(None)
                continue
            conversions = [
                self.conversion(
                    a, self.qualify(p.name, method.owner.file, method.owner)
                )
                for a, p in zip(actual, parameters, strict=True)
            ]
            if any(value is False for value in conversions):
                if method.varargs:
                    possible.append(method)
                    ranks.append(None)
                continue
            possible.append(method)
            unknown = (
                owner.inherits
                or owner.node.child_by_field_name("type_parameters") is not None
                or any(value is None for value in conversions)
                or method.node.child_by_field_name("type_parameters") is not None
            )
            ranks.append(None if unknown else conversions)
        target = None
        if possible and all(rank is not None for rank in ranks):
            winners = [
                i
                for i, rank in enumerate(ranks)
                if all(
                    i == j
                    or (
                        all(a <= b for a, b in zip(rank, other, strict=True))
                        and any(a < b for a, b in zip(rank, other, strict=True))
                    )
                    for j, other in enumerate(ranks)
                )
            ]
            if len(winners) == 1:
                target = possible[winners[0]]
        status = (
            "RESOLVED"
            if target
            else "AMBIGUOUS"
            if len(possible) > 1
            else "PARTIAL"
            if possible
            else "UNRESOLVED"
        )
        result = _Result(
            target,
            possible,
            status,
            "unique supported declared target"
            if target
            else "target applicability, receiver or conversion is outside supported coverage",
            selector,
            not declared,
        )
        self.memo[key] = result
        return result

    def analysis(self, file: _File) -> FileAnalysis:
        replacements = {}
        added = []
        dependencies = set()
        references = {
            e.source.id: e
            for e in file.result.analysis.entities
            if isinstance(e, Relation)
        }
        for site in self.sites.values():
            if site.file is not file:
                continue
            result = self.resolve(site)
            occurrence = site.occurrence
            target = result.target
            resolution = (
                Resolution(
                    status="RESOLVED",
                    target=EntityRef(
                        id=target.symbol.id, entity_type=EntityType.SYMBOL
                    ),
                )
                if target
                else Resolution(
                    status=result.status,
                    candidates=tuple(
                        EntityRef(id=m.symbol.id, entity_type=EntityType.SYMBOL)
                        for m in result.candidates
                    )
                    if result.status in ("AMBIGUOUS", "PARTIAL")
                    else (),
                    reason=result.reason,
                )
            )
            replacements[occurrence.id] = Occurrence.model_validate(
                {
                    **occurrence.model_dump(),
                    "resolution": "RESOLVED"
                    if target
                    else "AMBIGUOUS"
                    if result.status == "AMBIGUOUS"
                    else "UNRESOLVED",
                    "target_symbol_id": target.symbol.id if target else None,
                }
            )
            old_ref = references[occurrence.id]
            replacements[old_ref.id] = Relation.model_validate(
                {
                    **old_ref.model_dump(),
                    "resolution": resolution,
                    "certainty": Certainty.INFERRED if target else Certainty.UNKNOWN,
                    "coverage": self.coverage,
                }
            )
            evidence = Evidence(
                source_range=file.result._extractor.range(site.node),
                analyzer="java.calls",
                analyzer_version="1",
                rule="declared-method-applicability",
                description=result.reason,
            )
            relation_key = occurrence.logical_key + ":calls"
            added.append(
                Relation(
                    repository_id=occurrence.repository_id,
                    logical_key=relation_key,
                    id=logical_id(
                        occurrence.repository_id, EntityType.RELATION, relation_key
                    ),
                    name="CALLS",
                    relation_kind=RelationKind.CALLS,
                    source=EntityRef(
                        id=site.caller.symbol.id, entity_type=EntityType.SYMBOL
                    ),
                    resolution=resolution,
                    certainty=Certainty.INFERRED if target else Certainty.UNKNOWN,
                    evidence=(evidence,),
                    coverage=self.coverage,
                )
            )
            receiver, _ = self.receiver(site)
            if receiver in self.classes:
                path = self.classes[receiver].file.source.file.path
                if path != file.source.file.path:
                    dependencies.add(path)
            if result.external:
                external_key = occurrence.logical_key + ":external"
                external = ExternalReference(
                    repository_id=occurrence.repository_id,
                    logical_key=external_key,
                    id=logical_id(
                        occurrence.repository_id,
                        EntityType.EXTERNAL_REFERENCE,
                        external_key,
                    ),
                    name=occurrence.name,
                    source=EntityRef(
                        id=occurrence.id, entity_type=EntityType.OCCURRENCE
                    ),
                    selector=SymbolSelector(qualified_name=result.selector),
                    reason=result.reason,
                    evidence=(evidence,),
                    certainty=Certainty.UNKNOWN,
                    coverage=self.coverage,
                )
                added.append(external)
                dependency_key = external_key + ":dependency"
                added.append(
                    Relation(
                        repository_id=occurrence.repository_id,
                        logical_key=dependency_key,
                        id=logical_id(
                            occurrence.repository_id,
                            EntityType.RELATION,
                            dependency_key,
                        ),
                        name="EXTERNAL_DEPENDENCY",
                        relation_kind=RelationKind.EXTERNAL_DEPENDENCY,
                        source=EntityRef(
                            id=site.caller.symbol.id, entity_type=EntityType.SYMBOL
                        ),
                        resolution=Resolution(
                            status="RESOLVED",
                            target=EntityRef(
                                id=external.id,
                                entity_type=EntityType.EXTERNAL_REFERENCE,
                            ),
                        ),
                        certainty=Certainty.INFERRED,
                        evidence=(evidence,),
                        coverage=self.coverage,
                    )
                )
        return FileAnalysis(
            path=file.source.file.path,
            entities=tuple(
                replacements.get(e.id, e) for e in file.result.analysis.entities
            )
            + tuple(added),
            dependencies=tuple(sorted(dependencies)),
        )

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[FileAnalysis, ...]:
        def analyze() -> tuple[FileAnalysis, ...]:
            results = []
            for source in sources:
                context = self.files.get(source.file.path)
                if context is None or source != context.source:
                    raise ValueError(
                        "Java catalog does not match captured source; rebuild analyzer"
                    )
                results.append(self.analysis(context))
                tick("Java: анализ", len(sources))
            return tuple(results)

        return await asyncio.to_thread(analyze)


async def index_java(
    conn: asyncpg.Connection, repository_id: UUID, root: Path
) -> IncrementalResult:
    """Build a Java calls snapshot; validation/publication remain explicit caller actions."""
    root = await asyncio.to_thread(root.resolve, strict=True)
    captured = await _capture(root, repository_id, {".java": "java"})
    analyzer = await asyncio.to_thread(
        JavaCallAnalyzer,
        tuple(s for s in captured.sources if s.file.language == "java"),
    )
    return await index_incremental(
        conn,
        repository_id,
        root,
        analyzer,
        languages={".java": "java"},
        analysis_version=analyzer.analysis_version,
    )
