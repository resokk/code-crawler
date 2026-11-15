"""Captured-byte JavaScript/TypeScript syntax and conservative local module graphs."""

import asyncio
import json
import posixpath
import re
from dataclasses import dataclass, field
from importlib.metadata import version
from urllib.parse import urlsplit

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from code_crawler.incremental import FileAnalysis, SourceInput, _path
from code_crawler.source_adapters import (
    AdapterDescriptor,
    AdapterFileResult,
    PreparedAdapter,
    SourceRoute,
)
from code_crawler.ucm import (
    CallableSignature,
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    HttpSelector,
    Occurrence,
    Position,
    Relation,
    RelationKind,
    Resolution,
    Scope,
    SourceDiagnostic,
    SourceRange,
    Symbol,
    SymbolSelector,
    TypeRef,
    callable_key,
    logical_id,
)

VERSION = "2"
LIMITS = "syntax-only; no execution, package lookup, dynamic dispatch or compiler type inference"


def capabilities(language: str) -> tuple[Coverage, ...]:
    """Declare bounded syntax, binding and HTTP capabilities."""
    return tuple(
        Coverage(
            capability=f"{language}.{name}",
            analyzer_version=VERSION,
            status="PARTIAL",
            reasons=(LIMITS,),
        )
        for name in ("symbols", "references", "http")
    )


@dataclass(frozen=True)
class JavaScriptSourceAdapter:
    @property
    def descriptor(self) -> AdapterDescriptor:
        return _descriptor("javascript", (".js", ".jsx"))

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        return await asyncio.to_thread(_prepare, sources, "javascript")

    async def prepare_inventory(
        self, assigned: tuple[SourceInput, ...], inventory: tuple[SourceInput, ...]
    ) -> PreparedAdapter:
        """Resolve JS/TS imports using only registered captured source inventories."""
        sources = tuple(
            s
            for s in inventory
            if s.file.language in ("javascript", "typescript")
            or posixpath.basename(s.file.path) == "tsconfig.json"
        )
        return await asyncio.to_thread(_prepare, sources, "javascript")


@dataclass(frozen=True)
class TypeScriptSourceAdapter:
    include_json: bool = True

    @property
    def descriptor(self) -> AdapterDescriptor:
        # Config bytes must participate in capture and incremental dependencies.
        return _descriptor(
            "typescript",
            (".ts", ".tsx", ".json") if self.include_json else (".ts", ".tsx"),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        return await asyncio.to_thread(_prepare, sources, "typescript")

    async def prepare_inventory(
        self, assigned: tuple[SourceInput, ...], inventory: tuple[SourceInput, ...]
    ) -> PreparedAdapter:
        """Resolve JS/TS imports using only registered captured source inventories."""
        sources = tuple(
            s
            for s in inventory
            if s.file.language in ("javascript", "typescript")
            or posixpath.basename(s.file.path) == "tsconfig.json"
        )
        return await asyncio.to_thread(_prepare, sources, "typescript")


def _descriptor(language, suffixes):
    return AdapterDescriptor(
        key=language,
        version=VERSION,
        routes=tuple(SourceRoute(suffix=s, language=language) for s in suffixes),
        capabilities=capabilities(language),
        entity_types=(
            EntityType.SYMBOL,
            EntityType.SCOPE,
            EntityType.OCCURRENCE,
            EntityType.RELATION,
            EntityType.EXTERNAL_REFERENCE,
        ),
    )


def _walk(node):
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        pending.extend(reversed(current.named_children))


def _text(source, node):
    return (
        source.content[node.start_byte : node.end_byte].decode("utf-8") if node else ""
    )


def _string(source, node):
    if node is None or node.type not in ("string", "template_string"):
        return None
    raw = _text(source, node)
    if node.type == "template_string" and any(
        c.type == "template_substitution" for c in node.named_children
    ):
        return None
    # Escaped JS strings require evaluation semantics outside this bounded profile.
    return raw[1:-1] if "\\" not in raw else None


def _ref(entity):
    return EntityRef(entity_type=entity.entity_type, id=entity.id)


@dataclass
class _Unit:
    source: SourceInput
    language: str
    root: Node
    entities: list = field(default_factory=list)
    scopes: dict = field(default_factory=dict)
    bindings: dict = field(default_factory=dict)
    declarations: dict = field(default_factory=dict)
    exports: dict = field(default_factory=dict)
    imports: dict = field(default_factory=dict)
    dependencies: set = field(default_factory=set)
    diagnostics: list = field(default_factory=list)
    runtime_ids: set = field(default_factory=set)
    implementations: set = field(default_factory=set)
    writes: set = field(default_factory=set)
    type_exports: set = field(default_factory=set)
    assigned_names: set = field(default_factory=set)

    def text(self, node):
        return _text(self.source, node)

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
        return f"{self.source.file.path}:{tag}:{node.start_byte}"

    def add(self, entity):
        self.entities.append(entity)
        return entity

    def evidence(self, node, rule):
        return (
            Evidence(
                source_range=self.location(node),
                analyzer=self.language,
                analyzer_version=VERSION,
                rule=rule,
                description=self.text(node) or rule,
            ),
        )

    def relation(self, origin, target, node, kind, capability=1, reason=None):
        return self.add(
            Relation(
                **self.env(
                    EntityType.RELATION,
                    self.key(f"{kind}:{origin.id}", node),
                    kind.value,
                    node,
                ),
                relation_kind=kind,
                source=_ref(origin),
                resolution=Resolution(status="RESOLVED", target=_ref(target))
                if target
                else Resolution(
                    status="UNRESOLVED", reason=reason or "no unique lexical target"
                ),
                certainty=Certainty.STATIC_PROVEN if target else Certainty.UNKNOWN,
                evidence=self.evidence(node, kind.value),
                coverage=capabilities(self.language)[capability],
            )
        )

    def scope(self, node):
        current = node
        while current is not None:
            if current.id in self.scopes:
                return self.scopes[current.id]
            current = current.parent
        return self.scopes[self.root.id]

    def lookup(self, node, name):
        scope = self.scope(node)
        while scope:
            values = (
                self.bindings.get((scope.id, name), [])
                if scope.scope_kind != "TYPE"
                else []
            )
            if values:
                return values
            scope = next(
                (s for s in self.scopes.values() if s.id == scope.parent_scope_id), None
            )
        return []

    def occurrence(self, node, kind, target=None):
        occurrence = self.add(
            Occurrence(
                **self.env(
                    EntityType.OCCURRENCE,
                    self.key("occurrence:" + kind, node),
                    self.text(node) or kind,
                    node,
                ),
                occurrence_kind=kind,
                scope_id=self.scope(node).id,
                resolution="RESOLVED" if target else "UNRESOLVED",
                target_symbol_id=target.id if target else None,
            )
        )
        self.relation(
            occurrence,
            target,
            node,
            RelationKind.DECLARES if kind == "DECLARATION" else RelationKind.REFERENCES,
            0 if kind == "DECLARATION" else 1,
        )
        return occurrence

    def external(self, origin, node, selector, reason, http=False):
        reference = self.add(
            ExternalReference(
                **self.env(
                    EntityType.EXTERNAL_REFERENCE,
                    self.key("external", node),
                    self.text(node),
                    node,
                ),
                source=_ref(origin),
                selector=selector,
                reason=reason,
                evidence=self.evidence(
                    node, "http.client" if http else "module.selector"
                ),
                certainty=Certainty.UNKNOWN,
                coverage=capabilities(self.language)[2 if http else 1],
            )
        )
        self.relation(
            origin, reference, node, RelationKind.EXTERNAL_DEPENDENCY, 2 if http else 1
        )


def _pattern_names(node):
    if node.type in ("identifier", "shorthand_property_identifier_pattern"):
        yield node
    elif node.type in ("assignment_pattern", "object_assignment_pattern"):
        yield from _pattern_names(node.child_by_field_name("left"))
    elif node.type == "pair_pattern":
        yield from _pattern_names(node.child_by_field_name("value"))
    else:
        for child in node.named_children:
            yield from _pattern_names(child)


def _signature(unit, node):
    params = node.child_by_field_name("parameters")
    parameter = node.child_by_field_name("parameter")
    parameters = params.named_children if params else [parameter] if parameter else []
    types = []
    for param in parameters:
        annotation = param.child_by_field_name("type")
        types.append(
            TypeRef(
                name=unit.text(annotation).lstrip(": ") if annotation else "unknown"
            )
        )
    returns = node.child_by_field_name("return_type")
    return CallableSignature(
        parameter_types=tuple(types),
        return_type=TypeRef(name=unit.text(returns).lstrip(": ")) if returns else None,
    )


def _declare(unit):
    root = unit.root
    file_scope = unit.add(
        Scope(
            **unit.env(EntityType.SCOPE, unit.key("scope:FILE", root), "FILE", root),
            scope_kind="FILE",
        )
    )
    unit.scopes[root.id] = file_scope
    for node in _walk(root):
        parent_scope = unit.scope(node.parent) if node.parent else file_scope
        name = node.child_by_field_name("name")
        if (
            node.type == "variable_declarator"
            and node.parent.type == "variable_declaration"
        ):
            while parent_scope.scope_kind not in ("FILE", "CALLABLE"):
                parent_scope = next(
                    s
                    for s in unit.scopes.values()
                    if s.id == parent_scope.parent_scope_id
                )
        kind = None
        callable_node = node
        if node.type in (
            "class_declaration",
            "abstract_class_declaration",
            "interface_declaration",
            "type_alias_declaration",
            "enum_declaration",
        ):
            kind = "CLASS"
        elif node.type in (
            "function_declaration",
            "generator_function_declaration",
            "function_signature",
            "method_definition",
            "method_signature",
            "abstract_method_signature",
        ):
            kind = "METHOD"
        elif node.type == "variable_declarator":
            name = node.child_by_field_name("name")
            value = node.child_by_field_name("value")
            if value and value.type in (
                "arrow_function",
                "function_expression",
                "generator_function",
            ):
                kind, callable_node = "METHOD", value
            else:
                kind = "LOCAL_VARIABLE"
        elif (
            node.type
            in ("object_pattern", "array_pattern", "assignment_pattern", "rest_pattern")
            and node.parent
            and node.parent.type == "formal_parameters"
        ):
            name, kind = node, "PARAMETER"
        elif (
            node.type == "identifier"
            and node.parent
            and node.parent.type == "catch_clause"
            and node.parent.child_by_field_name("parameter") == node
        ):
            name, kind = node, "LOCAL_VARIABLE"
        elif (
            node.parent
            and node.parent.type == "for_in_statement"
            and node.parent.child_by_field_name("left") == node
            and node.parent.child_by_field_name("kind")
        ):
            name, kind = node, "LOCAL_VARIABLE"
            if unit.text(node.parent.child_by_field_name("kind")) == "var":
                while parent_scope.scope_kind not in ("FILE", "CALLABLE"):
                    parent_scope = next(
                        s
                        for s in unit.scopes.values()
                        if s.id == parent_scope.parent_scope_id
                    )
        elif node.type in ("required_parameter", "optional_parameter"):
            name = node.child_by_field_name("pattern")
            kind = "PARAMETER"
        elif (
            node.type == "identifier"
            and node.parent
            and (
                node.parent.type == "formal_parameters"
                or (
                    node.parent.type == "arrow_function"
                    and node.parent.child_by_field_name("parameter") == node
                )
            )
        ):
            name, kind = node, "PARAMETER"
        elif node.type in (
            "public_field_definition",
            "field_definition",
            "property_signature",
        ):
            kind = "FIELD"
        symbol = None
        if (
            kind
            and name
            and name.type
            in ("object_pattern", "array_pattern", "assignment_pattern", "rest_pattern")
        ):
            for binding in _pattern_names(name):
                spelling = unit.text(binding)
                declared = unit.add(
                    Symbol(
                        **unit.env(
                            EntityType.SYMBOL,
                            unit.key("symbol", binding),
                            spelling,
                            binding,
                        ),
                        symbol_kind="PARAMETER"
                        if kind == "PARAMETER"
                        else "LOCAL_VARIABLE",
                        qualified_name=f"{unit.source.file.path}::{spelling}",
                        scope_id=parent_scope.id,
                    )
                )
                unit.declarations[binding.id] = declared
                unit.bindings.setdefault((parent_scope.id, spelling), []).append(
                    declared
                )
                unit.occurrence(binding, "DECLARATION", declared)
        if (
            kind
            and name
            and name.type
            in (
                "identifier",
                "type_identifier",
                "property_identifier",
                "private_property_identifier",
            )
        ):
            spelling = unit.text(name)
            key = unit.key("symbol", name)
            extra = {}
            annotation = (
                node.child_by_field_name("type")
                or node.child_by_field_name("type_parameters")
                or callable_node.child_by_field_name("type_parameters")
            )
            if annotation:
                extra["type_ref"] = TypeRef(name=unit.text(annotation).lstrip(": "))
            if kind == "METHOD":
                signature = _signature(unit, callable_node)
                # Declaration offset distinguishes overload signatures and implementation.
                owner = unit.key("callable-owner", node)
                key = callable_key(owner, spelling, signature)
                extra.update(owner_key=owner, signature=signature)
            symbol = unit.add(
                Symbol(
                    **unit.env(EntityType.SYMBOL, key, spelling, name),
                    symbol_kind=kind,
                    qualified_name=f"{unit.source.file.path}::{spelling}",
                    scope_id=parent_scope.id,
                    **extra,
                )
            )
            unit.declarations[name.id] = symbol
            unit.bindings.setdefault((parent_scope.id, spelling), []).append(symbol)
            ancestor = node.parent
            if ancestor and ancestor.type in (
                "lexical_declaration",
                "variable_declaration",
            ):
                ancestor = ancestor.parent
            if ancestor and ancestor.type == "export_statement":
                export_name = (
                    "default"
                    if re.match(r"export\s+default\b", unit.text(ancestor))
                    else spelling
                )
                unit.exports.setdefault(export_name, []).append(symbol)
            unit.occurrence(name, "DECLARATION", symbol)
        scope_kind = None
        if node.type in (
            "class_declaration",
            "abstract_class_declaration",
            "interface_declaration",
        ):
            scope_kind = "TYPE"
        elif node.type in (
            "function_declaration",
            "generator_function_declaration",
            "function_signature",
            "method_definition",
            "method_signature",
            "abstract_method_signature",
            "arrow_function",
            "function_expression",
            "generator_function",
        ):
            scope_kind = "CALLABLE"
        elif node.type in (
            "statement_block",
            "catch_clause",
            "for_statement",
            "for_in_statement",
        ):
            scope_kind = "BLOCK"
        if scope_kind:
            if (
                symbol is None
                and node.parent
                and node.parent.type == "variable_declarator"
            ):
                declared_name = node.parent.child_by_field_name("name")
                symbol = (
                    unit.declarations.get(declared_name.id) if declared_name else None
                )
            if (
                scope_kind == "CALLABLE"
                and node.type
                in ("arrow_function", "function_expression", "generator_function")
                and symbol is None
            ):
                name_node = node.child_by_field_name("name")
                spelling = (
                    unit.text(name_node)
                    if name_node
                    else f"<anonymous@{node.start_byte}>"
                )
                owner = unit.key("callable-owner", node)
                signature = _signature(unit, node)
                symbol = unit.add(
                    Symbol(
                        **unit.env(
                            EntityType.SYMBOL,
                            callable_key(owner, spelling, signature),
                            spelling,
                            name_node or node,
                        ),
                        symbol_kind="METHOD",
                        qualified_name=f"{unit.source.file.path}::{spelling}",
                        scope_id=parent_scope.id,
                        owner_key=owner,
                        signature=signature,
                    )
                )
            if (
                symbol
                and scope_kind == "CALLABLE"
                and node.parent
                and node.parent.type == "export_statement"
                and re.match(r"export\s+default\b", unit.text(node.parent))
            ):
                unit.exports["default"] = [symbol]
            if symbol and scope_kind == "CALLABLE" and node.child_by_field_name("body"):
                unit.implementations.add(symbol.id)
            scope = unit.add(
                Scope(
                    **unit.env(
                        EntityType.SCOPE,
                        unit.key("scope:" + scope_kind, node),
                        scope_kind,
                        node,
                    ),
                    scope_kind=scope_kind,
                    parent_scope_id=parent_scope.id,
                    owner_symbol_id=symbol.id if symbol else None,
                )
            )
            unit.scopes[node.id] = scope
            if scope_kind == "CALLABLE" and node.type in (
                "function_expression",
                "generator_function",
            ):
                self_name = node.child_by_field_name("name")
                if self_name and symbol:
                    unit.bindings.setdefault(
                        (scope.id, unit.text(self_name)), []
                    ).append(symbol)
                    unit.declarations[self_name.id] = symbol
                    unit.occurrence(self_name, "DECLARATION", symbol)
            unit.relation(parent_scope, scope, node, RelationKind.CONTAINS, 0)


@dataclass(frozen=True)
class _ProjectConfig:
    base_url: str | None
    paths: tuple[tuple[str, tuple[str, ...]], ...]


def _config(unit):
    try:
        data = json.loads(unit.source.content)
        options = data.get("compilerOptions", {})
        if not isinstance(options, dict):
            raise TypeError("compilerOptions must be an object")
        base = options.get("baseUrl")
        paths = options.get("paths", {})
        if (
            (base is not None and not isinstance(base, str))
            or not isinstance(paths, dict)
            or any(
                not isinstance(k, str)
                or k.count("*") > 1
                or not isinstance(v, list)
                or not all(isinstance(x, str) and x.count("*") <= 1 for x in v)
                for k, v in paths.items()
            )
        ):
            raise ValueError("invalid baseUrl/paths")
        if "extends" in data or "references" in data:
            raise ValueError("tsconfig extends/project references are unsupported")
        return _ProjectConfig(
            base, tuple((k, tuple(v)) for k, v in sorted(paths.items()))
        )
    except (ValueError, TypeError, AttributeError) as error:
        unit.diagnostics.append(
            SourceDiagnostic(
                severity="ERROR", code="TS_CONFIG_UNSUPPORTED", message=str(error)
            )
        )
        return None


def _module(unit, specifier, units, configs):
    path = unit.source.file.path
    directory = posixpath.dirname(path)
    config_paths = []
    current = directory
    while True:
        config_paths.append(posixpath.join(current, "tsconfig.json"))
        if not current:
            break
        current = posixpath.dirname(current)
    unit.dependencies.update(config_paths)
    config_path = next((p for p in config_paths if p in configs), None)
    bases = []
    if specifier.startswith("."):
        bases = [posixpath.join(directory, specifier)]
    elif config_path and configs[config_path]:
        config = configs[config_path]
        base = config.base_url or "."
        aliases = config.paths
        config_dir = posixpath.dirname(config_path)
        for pattern, targets in sorted(
            aliases,
            key=lambda item: ("*" in item[0], -len(item[0].split("*")[0]), item[0]),
        ):
            match = re.fullmatch(re.escape(pattern).replace(r"\*", "(.*)"), specifier)
            if match:
                bases = [
                    posixpath.join(
                        config_dir,
                        base,
                        t.replace("*", match.group(1) if match.groups() else ""),
                    )
                    for t in targets
                ]
                break
        if not bases and config.base_url is not None:
            bases = [posixpath.join(config_dir, base, specifier)]
    candidates = []
    for base in bases:
        base = posixpath.normpath(base)
        if base.startswith(("../", "/")) or base == "..":
            continue
        options = [base]
        if unit.language == "typescript" and base.endswith((".js", ".jsx")):
            stem = base.rsplit(".", 1)[0]
            options = [stem + s for s in (".ts", ".tsx", ".d.ts")] + options
        options += [base + s for s in (".ts", ".tsx", ".js", ".jsx", ".d.ts")]
        options += [
            posixpath.join(base, "index") + s
            for s in (".ts", ".tsx", ".js", ".jsx", ".d.ts")
        ]
        safe_options = []
        for option in dict.fromkeys(posixpath.normpath(p) for p in options):
            try:
                _path(option)
            except ValueError:
                continue
            safe_options.append(option)
        options = safe_options
        unit.dependencies.update(options)
        found = next((p for p in options if p in units), None)
        if found:
            candidates.append(found)
    return units[candidates[0]] if len(set(candidates)) == 1 else None


def _imports(unit, units, configs, emit=True):
    for node in unit.root.named_children:
        if node.type != "import_statement":
            continue
        module = _string(unit.source, node.child_by_field_name("source"))
        target = _module(unit, module, units, configs) if module else None
        clause = next(
            (c for c in node.named_children if c.type == "import_clause"), None
        )
        for child in _walk(clause) if clause else ():
            imported, local = None, None
            if child.type == "import_specifier":
                imported = child.child_by_field_name("name")
                local = child.child_by_field_name("alias") or imported
            elif child.type == "identifier" and child.parent.type == "import_clause":
                imported, local = "default", child
            elif child.type == "namespace_import":
                local = child.named_children[-1]
                imported = "*"
            if local:
                imported_name = (
                    imported if isinstance(imported, str) else unit.text(imported)
                )
                type_only = bool(
                    re.match(r"import\s+type\b", unit.text(node))
                    or re.match(r"type\s", unit.text(child))
                )
                unit.imports[unit.text(local)] = (
                    target,
                    imported_name,
                    type_only,
                    module,
                )
                if not emit:
                    continue
                values = target.exports.get(imported_name, []) if target else []
                occurrence = unit.occurrence(
                    local, "REFERENCE", values[0] if len(values) == 1 else None
                )
                if not values and not (target and imported_name == "*"):
                    unit.external(
                        occurrence,
                        local,
                        SymbolSelector(qualified_name=f"{module}::{imported_name}"),
                        "module/export unavailable locally; deferred lookup",
                    )
        if clause is None and emit:
            occurrence = unit.occurrence(node, "REFERENCE")
            unit.external(
                occurrence,
                node,
                SymbolSelector(qualified_name=module or unit.text(node)),
                "side-effect import; runtime effects unsupported",
            )


def _exports(unit, units, configs):
    changed = False
    for node in unit.root.named_children:
        if node.type != "export_statement":
            continue
        module = _string(unit.source, node.child_by_field_name("source"))
        target = _module(unit, module, units, configs) if module else None
        clause = next(
            (c for c in node.named_children if c.type == "export_clause"), None
        )
        if clause:
            for item in clause.named_children:
                name = item.child_by_field_name("name")
                alias = item.child_by_field_name("alias") or name
                if not name:
                    continue
                values = (
                    target.exports.get(unit.text(name), [])
                    if target
                    else unit.lookup(item, unit.text(name))
                )
                imported = unit.imports.get(unit.text(name))
                if not values and not module and imported and imported[0]:
                    values = imported[0].exports.get(imported[1], [])
                if (
                    re.match(r"export\s+type\b", unit.text(node))
                    or re.match(r"type\s", unit.text(item))
                    or (target and unit.text(name) in target.type_exports)
                    or (
                        imported
                        and (
                            imported[2]
                            or (imported[0] and imported[1] in imported[0].type_exports)
                        )
                    )
                ):
                    unit.type_exports.add(unit.text(alias))
                if values and unit.exports.get(unit.text(alias)) != values:
                    unit.exports[unit.text(alias)] = values
                    changed = True
        elif re.match(r"export\s+default\b", unit.text(node)):
            value = node.child_by_field_name("value")
            if value and value.type == "identifier":
                values = unit.lookup(value, unit.text(value))
                if values and unit.exports.get("default") != values:
                    unit.exports["default"] = values
                    changed = True
        elif target and re.match(r"export\s*\*\s*from", unit.text(node)):
            for name, values in target.exports.items():
                if name != "default":
                    old = unit.exports.get(name, [])
                    merged = list({s.id: s for s in old + values}.values())
                    if merged != old:
                        unit.exports[name] = merged
                        changed = True
                    if name in target.type_exports:
                        unit.type_exports.add(name)
    return changed


def _export_references(unit, units, configs):
    for node in unit.root.named_children:
        if node.type != "export_statement":
            continue
        module = _string(unit.source, node.child_by_field_name("source"))
        target = _module(unit, module, units, configs) if module else None
        clause = next(
            (c for c in node.named_children if c.type == "export_clause"), None
        )
        if clause:
            for item in clause.named_children:
                name = item.child_by_field_name("name")
                if not name:
                    continue
                values = target.exports.get(unit.text(name), []) if target else []
                symbol = (
                    (values[0] if len(values) == 1 else None)
                    if module
                    else _target(unit, name)
                )
                occurrence = unit.occurrence(name, "REFERENCE", symbol)
                if module and not values:
                    unit.external(
                        occurrence,
                        name,
                        SymbolSelector(qualified_name=f"{module}::{unit.text(name)}"),
                        "reexport target unavailable locally; deferred lookup",
                    )
        elif module and target is None:
            occurrence = unit.occurrence(node, "REFERENCE")
            unit.external(
                occurrence,
                node,
                SymbolSelector(qualified_name=f"{module}::*"),
                "reexport module unavailable locally; deferred lookup",
            )


def _target(unit, node, call=False):
    if node.type == "member_expression":
        obj = node.child_by_field_name("object")
        member = node.child_by_field_name("property")
        if obj is None or member is None or unit.lookup(node, unit.text(obj)):
            return None
        binding = unit.imports.get(unit.text(obj))
        if not binding or binding[1] != "*" or (call and binding[2]):
            return None
        module = binding[0]
        name = unit.text(member)
        values = module.exports.get(name, []) if module else []
        if call and module and name in module.type_exports:
            return None
    elif node.type in ("identifier", "type_identifier"):
        name = unit.text(node)
        values = unit.lookup(node, name)
        if not values and name in unit.imports:
            module, imported, type_only, _ = unit.imports[name]
            if call and (type_only or (module and imported in module.type_exports)):
                return None
            values = module.exports.get(imported, []) if module else []
    else:
        return None
    if call:
        values = [
            s
            for s in values
            if s.symbol_kind == "METHOD"
            and s.id in unit.runtime_ids
            and s.id not in unit.writes
        ]
    return values[0] if len(values) == 1 else None


def _http(unit, call, origin):
    callee = call.child_by_field_name("function")
    args = call.child_by_field_name("arguments")
    arguments = args.named_children if args else []
    name = unit.text(callee)
    if (
        name == "fetch"
        and not unit.lookup(call, "fetch")
        and "fetch" not in unit.imports
        and "fetch" not in unit.assigned_names
    ):
        method, url = "GET", arguments[0] if arguments else None
        options = arguments[1] if len(arguments) > 1 else None
        if options:
            if options.type != "object":
                return
            for pair in options.named_children:
                if pair.type != "pair":
                    return
                key = unit.text(pair.child_by_field_name("key")).strip("\"'")
                if key == "method":
                    method = _string(unit.source, pair.child_by_field_name("value"))
    else:
        match = re.fullmatch(
            r"([A-Za-z_$][\w$]*)\.(get|post|put|patch|delete|head|options)", name
        )
        if not match:
            return
        binding = unit.imports.get(match[1])
        if (
            not binding
            or binding[3] != "axios"
            or binding[2]
            or binding[1] not in ("default", "*")
            or unit.lookup(call, match[1])
            or match[1] in unit.assigned_names
        ):
            return
        method, url = match[2].upper(), arguments[0] if arguments else None
    if not method or method.upper() not in (
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "TRACE",
        "CONNECT",
    ):
        return
    value = _string(unit.source, url)
    dynamic = value is None
    if dynamic and url and url.type == "template_string":
        value = "".join(
            "{dynamic}" if c.type == "template_substitution" else unit.text(c)
            for c in url.named_children
        )
        if any(c.type == "escape_sequence" for c in url.named_children):
            return
    if not value:
        return
    try:
        parsed = urlsplit(value)
    except ValueError:
        return
    if (
        not parsed.path.startswith("/")
        or (parsed.scheme and parsed.scheme not in ("http", "https"))
        or "{dynamic}" in parsed.netloc
    ):
        return
    unit.external(
        origin,
        call,
        HttpSelector(
            method=method.upper(),
            path=parsed.path,
            service=f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else None,
        ),
        "dynamic URL portions preserved; remote target deferred"
        if dynamic
        else "remote HTTP target deferred",
        True,
    )


def _references(unit):
    for node in _walk(unit.root):
        if node.type == "call_expression":
            callee = node.child_by_field_name("function")
            if callee is None:
                continue
            target = _target(unit, callee, True)
            occurrence = unit.occurrence(callee, "CALL", target)
            scope = unit.scope(node)
            while (
                scope and not scope.owner_symbol_id and scope.scope_kind != "CALLABLE"
            ):
                scope = next(
                    (s for s in unit.scopes.values() if s.id == scope.parent_scope_id),
                    None,
                )
            owner = next(
                (
                    s
                    for s in unit.entities
                    if isinstance(s, Symbol) and scope and s.id == scope.owner_symbol_id
                ),
                None,
            )
            if owner:
                unit.relation(owner, target, node, RelationKind.CALLS)
            if callee.type == "import":
                args = node.child_by_field_name("arguments")
                unit.external(
                    occurrence,
                    node,
                    SymbolSelector(qualified_name=unit.text(args) or "dynamic import"),
                    "dynamic import; not a static runtime binding",
                )
            else:
                _http(unit, node, occurrence)
        elif (
            node.type in ("identifier", "type_identifier")
            and node.id not in unit.declarations
        ):
            parent = node.parent
            if parent and (
                parent.type.startswith("import")
                or parent.type in ("namespace_import", "export_specifier")
            ):
                continue
            if any(a.type == "import_statement" for a in _ancestors(node)):
                continue
            if (
                parent
                and parent.type == "call_expression"
                and parent.child_by_field_name("function") == node
            ):
                continue
            unit.occurrence(node, "REFERENCE", _target(unit, node))


def _ancestors(node):
    current = node.parent
    while current:
        yield current
        current = current.parent


@dataclass(frozen=True)
class _Prepared:
    analysis_version: str
    results: dict

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        return tuple(self.results[s.file.path] for s in sources)


def _prepare(sources, language):
    units, configs, results = {}, {}, {}
    for source in sources:
        source_language = source.file.language
        path = source.file.path
        if path.endswith(".json"):
            unit = _Unit(source, source_language, None)
            if posixpath.basename(path) == "tsconfig.json":
                configs[path] = _config(unit)
            results[path] = AdapterFileResult(
                analysis=FileAnalysis(path=path),
                diagnostics=tuple(unit.diagnostics),
                capabilities=tuple(
                    c.model_copy(
                        update={
                            "status": "UNSUPPORTED",
                            "reasons": ("configuration only; no source facts",),
                        }
                    )
                    for c in capabilities(source_language)
                ),
            )
            continue
        if len(source.content) > 4_000_000:
            results[path] = AdapterFileResult(
                analysis=FileAnalysis(path=path),
                diagnostics=(
                    SourceDiagnostic(
                        severity="ERROR",
                        code="SOURCE_LIMIT",
                        message="source exceeds 4 MB parser budget",
                    ),
                ),
            )
            continue
        grammar = (
            tree_sitter_javascript.language()
            if source_language == "javascript"
            else tree_sitter_typescript.language_tsx()
            if path.endswith(".tsx")
            else tree_sitter_typescript.language_typescript()
        )
        root = Parser(Language(grammar)).parse(source.content).root_node
        unit = _Unit(source, source_language, root)
        if any(i >= 100_000 for i, _ in enumerate(_walk(root))):
            results[path] = AdapterFileResult(
                analysis=FileAnalysis(path=path),
                diagnostics=(
                    SourceDiagnostic(
                        severity="ERROR",
                        code="AST_LIMIT",
                        message="source exceeds 100000 AST node budget",
                    ),
                ),
            )
            continue
        if root.has_error:
            unit.diagnostics.append(
                SourceDiagnostic(
                    severity="ERROR",
                    code="SYNTAX_ERROR",
                    message="invalid source; semantic facts suppressed",
                    source_range=unit.location(root),
                )
            )
        else:
            _declare(unit)
        units[path] = unit
    for unit in units.values():
        if not unit.root.has_error:
            _imports(unit, units, configs, emit=False)
    for _ in range(len(units) + 1):
        changed = sum(
            _exports(u, units, configs) for u in units.values() if not u.root.has_error
        )
        if not changed:
            break
    runtime = set()
    writes = set()
    for unit in units.values():
        runtime.update(unit.implementations)
        for node in _walk(unit.root):
            name = node.child_by_field_name("name")
            if (
                name
                and node.child_by_field_name("body")
                and name.id in unit.declarations
            ):
                runtime.add(unit.declarations[name.id].id)
            if node.type == "variable_declarator":
                value = node.child_by_field_name("value")
                if (
                    name
                    and name.id in unit.declarations
                    and value
                    and value.type
                    in ("arrow_function", "function_expression", "generator_function")
                ):
                    runtime.add(unit.declarations[name.id].id)
        for node in _walk(unit.root):
            if node.type in (
                "assignment_expression",
                "augmented_assignment_expression",
                "update_expression",
            ):
                left = node.child_by_field_name("left") or node.child_by_field_name(
                    "argument"
                )
                if left:
                    unit.assigned_names.update(unit.text(n) for n in _walk(left))
                    writes.update(
                        s.id for n in _walk(left) for s in unit.lookup(n, unit.text(n))
                    )
    for unit in units.values():
        unit.runtime_ids = runtime
        unit.writes = writes
        if not unit.root.has_error:
            _imports(unit, units, configs)
            _export_references(unit, units, configs)
            _references(unit)
        results[unit.source.file.path] = AdapterFileResult(
            analysis=FileAnalysis(
                path=unit.source.file.path,
                entities=tuple(unit.entities),
                dependencies=tuple(sorted(unit.dependencies - {unit.source.file.path})),
            ),
            diagnostics=tuple(unit.diagnostics),
        )
    return _Prepared(
        f"{language}/{VERSION}:tree-sitter/{version('tree-sitter')}:"
        f"js/{version('tree-sitter-javascript')}:ts/{version('tree-sitter-typescript')}",
        results,
    )
