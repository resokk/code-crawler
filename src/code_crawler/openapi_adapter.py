"""Bounded captured-byte OpenAPI contracts; references are edges, never expansion."""

import asyncio
import hashlib
import json
import math
import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit

import yaml
from yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    ScalarEvent,
)
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.source_adapters import (
    AdapterCatalog,
    AdapterDescriptor,
    AdapterFileResult,
    PreparedAdapter,
    SourceRoute,
)
from code_crawler.ucm import (
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    Position,
    Relation,
    RelationKind,
    Resolution,
    SourceDiagnostic,
    SourceFile,
    SourceRange,
    Symbol,
    SymbolSelector,
    Value,
    logical_id,
)

VERSION = "openapi/1"
MAX_BYTES = 4 * 1024 * 1024
MAX_DEPTH = 64
MAX_NODES = 20000
CAPABILITY = Coverage(
    capability="openapi.contracts",
    analyzer_version=VERSION,
    status="PARTIAL",
    reasons=(
        "Contracts only; runtime, vendor extensions and dynamic JSON Schema semantics are not inferred.",
    ),
)
KINDS = (
    "OPENAPI_DOCUMENT",
    "OPENAPI_OPERATION",
    "OPENAPI_PARAMETER",
    "OPENAPI_SCHEMA",
    "OPENAPI_FIELD",
    "OPENAPI_RESPONSE",
    "OPENAPI_BODY",
    "OPENAPI_MEDIA_TYPE",
    "OPENAPI_SECURITY",
    "OPENAPI_CALLBACK",
    "OPENAPI_WEBHOOK",
    "OPENAPI_ELEMENT",
)
METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _pointer(parts: tuple[str, ...]) -> str:
    return "".join("/" + p.replace("~", "~0").replace("/", "~1") for p in parts)


def _scalar(node: ScalarNode) -> str | int | float | bool | None:
    value = node.value
    if node.tag.endswith(":null"):
        return None
    if node.tag.endswith(":bool") and value.lower() in ("true", "false"):
        return value.lower() == "true"
    if node.tag.endswith((":int", ":float")) and re.fullmatch(
        r"-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?", value
    ):
        result = json.loads(value)
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("non-finite number")
        return result
    return value


@dataclass
class _Document:
    source: SourceInput
    nodes: dict[tuple[str, ...], object]
    values: dict[tuple[str, ...], object]
    version: str | None
    text_lines: list[str]

    def location(self, parts: tuple[str, ...]) -> SourceRange:
        node = self.nodes[parts]

        def position(mark) -> Position:
            line = (
                self.text_lines[mark.line] if mark.line < len(self.text_lines) else ""
            )
            return Position(
                line=mark.line + 1, byte_column=len(line[: mark.column].encode("utf-8"))
            )

        return SourceRange(
            source_file_id=self.source.file.id,
            start=position(node.start_mark),
            end=position(node.end_mark),
        )


def _parse(source: SourceInput) -> _Document:
    if len(source.content) > MAX_BYTES:
        raise ValueError("document exceeds 4 MiB")
    text = source.content.decode("utf-8-sig")
    if text.startswith("\ufeff") or b"\0" in source.content:
        raise ValueError("NUL/unsupported encoding")
    # Keep BOM coordinates in the original byte stream.
    if source.content.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 BOM is unsupported")
    if source.file.path.endswith(".json"):

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result

        def invalid(value):
            raise ValueError("non-finite JSON number")

        json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
    count = depth = 0
    for event in yaml.parse(text, Loader=yaml.SafeLoader):
        if isinstance(event, AliasEvent):
            raise TypeError("YAML alias expansion is forbidden")
        if isinstance(event, CollectionStartEvent):
            depth += 1
        if isinstance(event, CollectionEndEvent):
            depth -= 1
        if isinstance(event, (ScalarEvent, CollectionStartEvent)):
            count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise ValueError("document depth/node budget exceeded")
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    if root is None:
        raise ValueError("empty document")
    nodes, values = {}, {}

    def visit(node, parts):
        if node.tag not in {
            "tag:yaml.org,2002:" + t
            for t in ("map", "seq", "str", "bool", "null", "int", "float", "timestamp")
        }:
            raise ValueError("unsupported YAML tag")
        nodes[parts] = node
        if isinstance(node, MappingNode):
            seen = set()
            for key, child in node.value:
                if (
                    not isinstance(key, ScalarNode)
                    or key.value in seen
                    or key.tag
                    not in {
                        "tag:yaml.org,2002:" + t
                        for t in (
                            "str",
                            "int",
                            "bool",
                            "null",
                            "float",
                            "timestamp",
                            "merge",
                        )
                    }
                ):
                    raise ValueError("duplicate or non-scalar mapping key")
                seen.add(key.value)
                visit(child, (*parts, key.value))
        elif isinstance(node, SequenceNode):
            for index, child in enumerate(node.value):
                visit(child, (*parts, str(index)))
        else:
            values[parts] = _scalar(node)

    visit(root, ())
    version = values.get(("openapi",))
    return _Document(
        source,
        nodes,
        values,
        version if isinstance(version, str) else None,
        text.splitlines(keepends=True),
    )


def _target(path: str, reference: str) -> tuple[str, tuple[str, ...]] | None:
    if any(ord(char) < 32 for char in reference):
        raise ValueError("control character in reference")
    uri = urlsplit(reference)
    if uri.scheme or uri.netloc:
        return None
    if uri.query:
        raise ValueError("reference query is unsupported")
    relative = unquote(uri.path)
    if relative.startswith("/") or any(c in relative for c in ("\\", "\0", ":")):
        raise ValueError("reference escapes repository")
    target = (
        posixpath.normpath(posixpath.join(posixpath.dirname(path), relative))
        if relative
        else path
    )
    if target in (".", "..") or target.startswith(("../", "/")):
        raise ValueError("reference escapes repository")
    fragment = unquote(uri.fragment)
    if fragment and not fragment.startswith("/"):
        # Anchors require dialect-aware lookup; handled by the caller.
        return target, ("#" + fragment,)
    parts = tuple(fragment[1:].split("/")) if fragment else ()
    if any(re.search(r"~(?![01])", part) for part in parts):
        raise ValueError("invalid JSON pointer escape")
    return target, tuple(p.replace("~1", "/").replace("~0", "~") for p in parts)


def _data(parts: tuple[str, ...]) -> bool:
    return any(
        (
            part in ("example", "examples", "default", "enum", "const")
            or part.startswith("x-")
        )
        and (index == 0 or parts[index - 1] not in ("properties", "schemas", "$defs"))
        for index, part in enumerate(parts)
    )


def _base_changed(doc: _Document, parts: tuple[str, ...]) -> bool:
    return any((*parts[:i], "$id") in doc.nodes for i in range(len(parts)))


def _ref_key(parts: tuple[str, ...]) -> bool:
    return (
        bool(parts)
        and not _data(parts)
        and (
            parts[-1] == "$ref"
            or (len(parts) >= 3 and parts[-3:-1] == ("discriminator", "mapping"))
        )
    )


def _ref_text(parts: tuple[str, ...], value: str) -> str:
    if parts[-1] != "$ref" and not any(c in value for c in "/#.:"):
        return "#/components/schemas/" + value.replace("~", "~0").replace("/", "~1")
    return value


def _kind(parts: tuple[str, ...], nodes: dict) -> str:
    if not parts:
        return "OPENAPI_DOCUMENT"
    if _data(parts):
        return "OPENAPI_ELEMENT"
    key = parts[-1]
    operation_parent = parts[:-1]
    if len(operation_parent) >= 3 and operation_parent[-1] == "additionalOperations":
        operation_parent = operation_parent[:-1]
    path_item = (
        len(operation_parent) == 2 and operation_parent[0] in ("paths", "webhooks")
    ) or (len(operation_parent) >= 3 and operation_parent[-3] == "callbacks")
    if path_item and (
        key in METHODS or key == "query" or parts[-2] == "additionalOperations"
    ):
        return "OPENAPI_OPERATION"
    if len(parts) >= 2:
        parent = parts[-2]
        if parent == "properties":
            return "OPENAPI_FIELD"
        if (
            parent == "schemas"
            or key
            in (
                "schema",
                "items",
                "additionalProperties",
                "not",
                "if",
                "then",
                "else",
                "contains",
                "unevaluatedProperties",
            )
            or parent
            in ("allOf", "anyOf", "oneOf", "prefixItems", "$defs", "dependentSchemas")
        ):
            return "OPENAPI_SCHEMA"
        if parent == "parameters":
            return "OPENAPI_PARAMETER"
        if parent == "responses":
            return "OPENAPI_RESPONSE"
        if parent == "requestBodies" or key == "requestBody":
            return "OPENAPI_BODY"
        if parent == "content":
            return "OPENAPI_MEDIA_TYPE"
        if parent in ("securitySchemes", "security"):
            return "OPENAPI_SECURITY"
        if parent == "callbacks":
            return "OPENAPI_CALLBACK"
        if parent == "webhooks":
            return "OPENAPI_WEBHOOK"
    return "OPENAPI_ELEMENT"


@dataclass(frozen=True)
class OpenApiSourceAdapter:
    @property
    def descriptor(self) -> AdapterDescriptor:
        from code_crawler.openapi_bindings import COVERAGE

        return AdapterDescriptor(
            key="openapi",
            version="openapi/2",
            routes=tuple(
                SourceRoute(suffix=suffix, language="openapi")
                for suffix in (".json", ".yaml", ".yml")
            ),
            capabilities=(CAPABILITY, COVERAGE),
            entity_types=(
                EntityType.SYMBOL,
                EntityType.VALUE,
                EntityType.RELATION,
                EntityType.EXTERNAL_REFERENCE,
            ),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        return await asyncio.to_thread(_prepare, sources)


@dataclass(frozen=True)
class _Prepared:
    results: dict[str, AdapterFileResult]
    analysis_version: str = VERSION
    documents: dict = field(default_factory=dict)
    bound: bool = False
    binding_requested: bool = False
    source_files: tuple[SourceFile, ...] = ()

    @property
    def catalog_keys(self) -> tuple[str, ...]:
        from code_crawler.java_http_catalog import CATALOG_KEY

        return (CATALOG_KEY,) if self.binding_requested else ()

    async def with_catalogs(
        self, catalogs: Mapping[str, AdapterCatalog]
    ) -> "_Prepared":
        from code_crawler.java_http_catalog import CATALOG_KEY, JavaHttpCatalog
        from code_crawler.openapi_bindings import VERSION as BINDINGS_VERSION
        from code_crawler.openapi_bindings import bind_results

        catalog = catalogs.get(CATALOG_KEY)
        if catalog is not None and not isinstance(catalog, JavaHttpCatalog):
            raise TypeError("OpenAPI requires a typed JavaHttpCatalog")
        results = await asyncio.to_thread(
            bind_results, self.results, self.documents, catalog
        )
        config_hash = hashlib.sha256(
            json.dumps(
                [
                    (file.path, file.content_sha256)
                    for file in self.source_files
                    if posixpath.basename(file.path).startswith("application")
                ]
            ).encode()
        ).hexdigest()
        version = (
            self.analysis_version
            + ":"
            + BINDINGS_VERSION
            + ":"
            + (catalog.version if catalog else "no-java")
            + ":"
            + config_hash
        )
        return _Prepared(
            results,
            version,
            self.documents,
            True,
            self.binding_requested,
            self.source_files,
        )

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        if not self.bound:
            from code_crawler.openapi_bindings import bind_results

            results = await asyncio.to_thread(
                bind_results,
                {s.file.path: self.results[s.file.path] for s in sources},
                self.documents,
                None,
            )
            return tuple(results[s.file.path] for s in sources)
        return tuple(self.results[s.file.path] for s in sources)


def _prepare(sources: tuple[SourceInput, ...]) -> _Prepared:
    docs, errors = {}, {}
    for source in sources:
        try:
            docs[source.file.path] = _parse(source)
        except (
            ValueError,
            TypeError,
            yaml.YAMLError,
            UnicodeError,
            RecursionError,
        ) as error:
            errors[source.file.path] = str(error)
    active = {
        path
        for path, doc in docs.items()
        if doc.version and re.fullmatch(r"3\.[012]\.\d+", doc.version)
    }
    dependencies = {path: set() for path in docs}
    pending = sorted(active)
    while pending:
        path = pending.pop()
        doc = docs[path]
        for parts, value in doc.values.items():
            if (
                _ref_key(parts)
                and isinstance(value, str)
                and not _base_changed(doc, parts)
            ):
                try:
                    target = _target(path, _ref_text(parts, value))
                except ValueError:
                    continue
                if target:
                    target_path, _ = target
                    if target_path != path:
                        dependencies[path].add(target_path)
                    if target_path in docs and target_path not in active:
                        # An explicit unsupported OpenAPI version is not a schema fragment.
                        if ("openapi",) in docs[target_path].nodes:
                            continue
                        active.add(target_path)
                        pending.append(target_path)
    symbols = {}

    def base(doc, kind, key, name, parts):
        logical_key = json.dumps(
            ["openapi", doc.source.file.path, key],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return {
            "repository_id": doc.source.file.repository_id,
            "id": logical_id(doc.source.file.repository_id, kind, logical_key),
            "logical_key": logical_key,
            "name": name or "/",
            "source_range": doc.location(parts),
        }

    for path in sorted(active):
        doc = docs[path]
        for parts in sorted(doc.nodes):
            symbols[path, parts] = Symbol(
                **base(
                    doc,
                    EntityType.SYMBOL,
                    ["node", _pointer(parts)],
                    parts[-1] if parts else path,
                    parts,
                ),
                symbol_kind="OPENAPI_SCHEMA"
                if not parts and doc.version is None
                else _kind(parts, doc.nodes),
                qualified_name=path + "#" + _pointer(parts),
            )
    identity = json.dumps([(path, docs[path].version) for path in sorted(active)])
    from code_crawler.openapi_bindings import has_operations

    results = {
        source.file.path: _emit(
            source, docs, errors, active, dependencies, symbols, base
        )
        for source in sources
    }
    return _Prepared(
        results,
        "openapi/2:" + hashlib.sha256(identity.encode()).hexdigest(),
        docs,
        False,
        has_operations(results),
        tuple(s.file for s in sources),
    )


def _emit(
    source, docs, errors, active, dependencies, symbols, base
) -> AdapterFileResult:
    path = source.file.path
    doc = docs.get(path)
    diagnostics = []
    entities = []

    def diagnostic(code, message, parts=()):
        diagnostics.append(
            SourceDiagnostic(
                severity="WARNING",
                code="openapi." + code,
                message=message,
                source_range=doc.location(parts) if doc else None,
            )
        )

    if path not in active:
        if path in errors:
            diagnostic("INVALID_DOCUMENT", errors[path])
        elif doc and ("openapi",) in doc.nodes:
            diagnostic(
                "UNSUPPORTED_VERSION",
                "Expected root openapi 3.0.x, 3.1.x or 3.2.x.",
            )
        return AdapterFileResult(
            analysis=FileAnalysis(path=path),
            diagnostics=tuple(diagnostics),
            capabilities=(
                CAPABILITY.model_copy(
                    update={
                        "status": "UNSUPPORTED",
                        "reasons": (
                            "Not a supported OpenAPI root or referenced fragment.",
                        ),
                    }
                ),
            ),
        )

    def ref(entity):
        return EntityRef(id=entity.id, entity_type=entity.entity_type)

    def evidence(parts, rule):
        return (
            Evidence(
                source_range=doc.location(parts),
                analyzer="openapi",
                analyzer_version=VERSION,
                rule=rule,
                description="Explicit contract syntax; no runtime dependency inferred.",
            ),
        )

    def relation(
        kind, origin, target, parts, status="RESOLVED", reason=None, candidates=()
    ):
        entities.append(
            Relation(
                **base(
                    doc,
                    EntityType.RELATION,
                    [
                        kind.value,
                        origin.id,
                        _pointer(parts),
                        target.id if target else None,
                    ],
                    kind.value,
                    parts,
                ),
                relation_kind=kind,
                source=ref(origin),
                resolution=Resolution(
                    status=status,
                    target=ref(target) if target else None,
                    reason=reason,
                    candidates=tuple(ref(c) for c in candidates),
                ),
                certainty=Certainty.STATIC_PROVEN if target else Certainty.UNKNOWN,
                evidence=evidence(parts, kind.value),
                coverage=CAPABILITY,
            )
        )

    def literal(origin, name, value, parts, identity):
        item = Value(
            **base(doc, EntityType.VALUE, identity, name, parts),
            value_kind="LITERAL",
            literal=value,
        )
        entities.append(item)
        relation(RelationKind.OPENAPI_ATTRIBUTE, origin, item, parts)

    for parts in sorted(doc.nodes):
        symbol = symbols[path, parts]
        entities.append(symbol)
        if symbol.symbol_kind != "OPENAPI_ELEMENT" and not isinstance(
            doc.nodes[parts], MappingNode
        ):
            boolean_schema = symbol.symbol_kind in (
                "OPENAPI_SCHEMA",
                "OPENAPI_FIELD",
            ) and isinstance(doc.values.get(parts), bool)
            if not boolean_schema:
                diagnostic(
                    "INVALID_SHAPE", "Expected an object at this contract node.", parts
                )
        if parts:
            relation(RelationKind.CONTAINS, symbols[path, parts[:-1]], symbol, parts)
        if parts in doc.values:
            literal(
                symbol,
                parts[-1] if parts else "value",
                doc.values[parts],
                parts,
                ["value", _pointer(parts)],
            )
        if symbol.symbol_kind == "OPENAPI_DOCUMENT":
            literal(symbol, "dialect", doc.version or "fragment", parts, ["dialect"])
        if symbol.symbol_kind == "OPENAPI_OPERATION":
            method = parts[-1].upper()
            if "additionalOperations" in parts:
                method = parts[-1]
            # Operation ancestry includes callback expressions and webhook names.
            route = parts[-3] if parts[-2] == "additionalOperations" else parts[-2]
            literal(symbol, "method", method, parts, ["method", _pointer(parts)])
            literal(symbol, "path", route, parts, ["path", _pointer(parts)])
            if (
                (method == "QUERY" or "additionalOperations" in parts)
                and doc.version
                and not doc.version.startswith("3.2.")
            ):
                diagnostic(
                    "DIALECT",
                    "QUERY/additionalOperations requires OpenAPI 3.2.",
                    parts,
                )
        if not parts:
            continue
        key, value = parts[-1], doc.values.get(parts)
        if key.startswith("x-") and _data(parts):
            diagnostic(
                "VENDOR_EXTENSION",
                "Vendor extension preserved without interpretation.",
                parts,
            )
        if _data(parts):
            continue
        if key in ("$id", "$dynamicRef", "$dynamicAnchor"):
            diagnostic(
                "DYNAMIC_SCHEMA",
                "JSON Schema base/dynamic scope is preserved, not evaluated.",
                parts,
            )
        if (
            doc.version
            and doc.version.startswith("3.0.")
            and (
                key in ("webhooks", "$schema", "$anchor")
                or (key == "type" and isinstance(doc.nodes[parts], SequenceNode))
                or (
                    symbol.symbol_kind in ("OPENAPI_SCHEMA", "OPENAPI_FIELD")
                    and isinstance(value, bool)
                )
            )
        ):
            diagnostic(
                "DIALECT",
                "JSON Schema unions/boolean schemas/anchors and webhooks require OpenAPI 3.1+.",
                parts,
            )
        if key == "nullable" and doc.version and not doc.version.startswith("3.0."):
            diagnostic(
                "DIALECT",
                "nullable is not JSON Schema null-union semantics in OpenAPI 3.1/3.2.",
                parts,
            )
        if (
            key == "in"
            and value == "querystring"
            and doc.version
            and not doc.version.startswith("3.2.")
        ):
            diagnostic("DIALECT", "querystring requires OpenAPI 3.2.", parts)
        if not _ref_key(parts):
            continue
        if not isinstance(value, str) or not value.strip():
            diagnostic("INVALID_REF", "$ref must be a nonempty string.", parts)
            continue
        origin = symbols[path, parts[:-1]]
        try:
            target = _target(path, _ref_text(parts, value))
        except ValueError as error:
            diagnostic("UNSAFE_REF", str(error), parts)
            relation(
                RelationKind.OPENAPI_REF,
                origin,
                None,
                parts,
                "UNRESOLVED",
                "Unsafe or unsupported reference",
            )
            continue
        base_changed = _base_changed(doc, parts)
        if target is None or base_changed:
            entities.append(
                ExternalReference(
                    **base(
                        doc,
                        EntityType.EXTERNAL_REFERENCE,
                        ["external", _pointer(parts)],
                        "$ref",
                        parts,
                    ),
                    source=ref(origin),
                    selector=SymbolSelector(qualified_name="openapi.ref::" + value),
                    reason="Deferred URI/base-scope reference; no network or external repository read.",
                    certainty=Certainty.UNKNOWN,
                    evidence=evidence(parts, "openapi.deferred-ref"),
                    coverage=CAPABILITY,
                )
            )
            continue
        target_path, target_parts = target
        candidates = []
        if (
            len(target_parts) == 1
            and target_parts[0].startswith("#")
            and target_path in active
            and not (doc.version and doc.version.startswith("3.0."))
        ):
            anchor = target_parts[0][1:]
            candidates = [
                symbols[target_path, p[:-1]]
                for p, v in docs[target_path].values.items()
                if p
                and p[-1] == "$anchor"
                and v == anchor
                and not _base_changed(docs[target_path], p)
                and not _data(p)
            ]
            candidates.sort(key=lambda candidate: candidate.id)
            resolved = candidates[0] if len(candidates) == 1 else None
        else:
            resolved = symbols.get((target_path, target_parts))
        relation(
            RelationKind.OPENAPI_REF,
            origin,
            resolved,
            parts,
            "RESOLVED"
            if resolved
            else "AMBIGUOUS"
            if len(candidates) > 1
            else "UNRESOLVED",
            None if resolved else "Missing or ambiguous captured reference target",
            candidates if len(candidates) > 1 else (),
        )
        if resolved is None:
            diagnostic(
                "UNRESOLVED_REF",
                "Reference target is missing or ambiguous in captured inventory.",
                parts,
            )
    return AdapterFileResult(
        analysis=FileAnalysis(
            path=path,
            entities=tuple(entities),
            dependencies=tuple(sorted(dependencies[path])),
        ),
        diagnostics=tuple(diagnostics),
        capabilities=(CAPABILITY,),
    )
