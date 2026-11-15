"""Shared read-only declaration/import view over canonical Java extractor results."""

import re
from collections import defaultdict
from dataclasses import dataclass

from tree_sitter import Node

from code_crawler import java
from code_crawler.incremental import SourceInput
from code_crawler.java_calls import _erase
from code_crawler.java_symbols import JavaSymbolsResult
from code_crawler.ucm import Evidence, SourceRange, Symbol


@dataclass
class JavaUnit:
    source: SourceInput
    result: JavaSymbolsResult
    package: str
    imports: dict[str, list[str]]
    wildcards: tuple[str, ...]


@dataclass
class JavaType:
    unit: JavaUnit
    symbol: Symbol
    node: Node


class JavaDeclarationCatalog:
    def __init__(
        self,
        sources: tuple[tuple[SourceInput, JavaSymbolsResult], ...],
        known_types: frozenset[str],
        analyzer: str,
        version: str,
    ) -> None:
        self.known_types = known_types
        self.analyzer = analyzer
        self.version = version
        self.types: dict[str, list[JavaType]] = defaultdict(list)
        self.by_key: dict[str, JavaType] = {}
        self.methods: dict[str, list[tuple[Symbol, Node]]] = defaultdict(list)
        self.failed = []
        for source, result in sources:
            if result.diagnostics:
                self.failed.append(source.file.path)
                continue
            root = result._extractor.parsed._tree.root_node
            package = next(
                (
                    java._text(n.named_children[-1])
                    for n in root.named_children
                    if n.type == "package_declaration"
                ),
                "",
            )
            imports: dict[str, list[str]] = defaultdict(list)
            wildcards = []
            for node in root.named_children:
                if node.type != "import_declaration":
                    continue
                text = java._text(node)
                if match := re.fullmatch(r"import\s+([\w.$]+)\s*;", text):
                    imports[match[1].rsplit(".", 1)[-1]].append(match[1])
                elif match := re.fullmatch(r"import\s+([\w.$]+)\.\*\s*;", text):
                    wildcards.append(match[1])
            unit = JavaUnit(source, result, package, dict(imports), tuple(wildcards))
            for symbol in result.declared:
                if not isinstance(symbol, Symbol):
                    continue
                node = result._extractor.symbol_nodes[symbol.id]
                if symbol.symbol_kind == "CLASS" and symbol.logical_key.startswith(
                    "java:type:"
                ):
                    info = JavaType(unit, symbol, node)
                    self.types[symbol.qualified_name].append(info)
                    self.by_key[symbol.logical_key] = info
                elif symbol.symbol_kind == "METHOD":
                    self.methods[symbol.owner_key].append((symbol, node))

    def qualify(self, name: str, owner: JavaType) -> str | None:
        name = _erase(name)
        if name in ("void", "boolean", "int", "long"):
            return name
        known = self.types.keys() | self.known_types
        if name in known:
            return name
        package_name = f"{owner.unit.package}.{name}".lstrip(".")
        if package_name in self.types:
            return package_name
        outer = owner.symbol.qualified_name
        while outer:
            if (nested := outer + "." + name) in self.types:
                return nested
            outer = outer.rpartition(".")[0]
        head, _, tail = name.partition(".")
        imported = owner.unit.imports.get(head, [])
        if imported:
            options = {item + ("." + tail if tail else "") for item in imported}
            return (
                next(iter(options)) if len(options) == 1 and options <= known else None
            )
        if len(owner.unit.wildcards) == 1:
            qualified = owner.unit.wildcards[0] + "." + name
            return qualified if qualified in known else None
        return None

    def annotations(self, node: Node, owner: JavaType) -> tuple[tuple[str, Node], ...]:
        modifiers = next(
            (c for c in node.named_children if c.type == "modifiers"), None
        )
        found = []
        for child in modifiers.named_children if modifiers else ():
            if child.type in ("annotation", "marker_annotation"):
                name = self.qualify(
                    java._text(child.child_by_field_name("name")), owner
                )
                if name in self.known_types and name not in self.types:
                    found.append((name, child))
        return tuple(found)

    def bases(self, owner: JavaType) -> tuple[str, ...]:
        result = []
        for child in owner.node.named_children:
            if child.type not in (
                "superclass",
                "super_interfaces",
                "extends_interfaces",
            ):
                continue
            nodes = child.named_children
            if nodes and nodes[0].type == "type_list":
                nodes = nodes[0].named_children
            for node in nodes:
                if name := self.qualify(java._text(node), owner):
                    result.append(name)
        return tuple(result)

    def evidence(self, owner: JavaType, node: Node, rule: str) -> Evidence:
        return Evidence(
            source_range=SourceRange(
                source_file_id=owner.unit.source.file.id,
                start=java._span(node).start,
                end=java._span(node).end,
            ),
            analyzer=self.analyzer,
            analyzer_version=self.version,
            rule=rule,
            description="Declared Java syntax; runtime registration and execution are not asserted.",
        )
