"""Local OpenAPI/Spring bindings with explicit candidates, context and DTO evidence."""

import posixpath
from collections import defaultdict
from collections.abc import Mapping
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from yaml.nodes import MappingNode

from code_crawler.incremental import FileAnalysis
from code_crawler.java_http_catalog import (
    HTTP_METHODS,
    JavaHttpCatalog,
    JavaHttpRoute,
    join_path,
)
from code_crawler.source_adapters import AdapterFileResult
from code_crawler.ucm import (
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    HttpSelector,
    Relation,
    RelationKind,
    Resolution,
    SourceDiagnostic,
    Symbol,
    SymbolSelector,
    Value,
    logical_id,
)

if TYPE_CHECKING:
    from code_crawler.openapi_adapter import _Document

VERSION = "openapi.java/1"
COVERAGE = Coverage(
    capability="openapi.java.bindings",
    analyzer_version=VERSION,
    status="PARTIAL",
    reasons=(
        "Closed captured Spring annotation subset; runtime deployment, dispatch and serialization are not proved.",
    ),
)


def route_key(path: str | None) -> tuple[str | None, tuple[str, ...], bool]:
    """Normalize whole-segment variable names, preserving slash and regex uncertainty."""
    if (
        path is None
        or not path.startswith("/")
        or any(ord(c) < 32 for c in path)
        or any(c in path for c in ("?", "#", "\\", "*", "${"))
    ):
        return None, (), True
    names = []
    normalized = []
    uncertain = False
    for segment in path.split("/"):
        if "{" in segment or "}" in segment:
            if not (
                segment.startswith("{")
                and segment.endswith("}")
                and segment.count("{") == segment.count("}") == 1
            ):
                return None, (), True
            name, sep, _pattern = segment[1:-1].partition(":")
            if not name:
                return None, (), True
            names.append(name)
            normalized.append("{}")
            uncertain |= bool(sep)
        else:
            if segment in (".", ".."):
                return None, (), True
            normalized.append(segment)
    uncertain |= len(set(names)) != len(names)
    return "/".join(normalized), tuple(names), uncertain


def _parts(symbol: Symbol, path: str) -> tuple[str, ...]:
    pointer = symbol.qualified_name.removeprefix(path + "#")
    return tuple(
        part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]
    )


def has_operations(results: Mapping[str, AdapterFileResult]) -> bool:
    return any(
        isinstance(e, Symbol)
        and e.symbol_kind == "OPENAPI_OPERATION"
        and _parts(e, path)[:1] == ("paths",)
        for path, result in results.items()
        for e in result.analysis.entities
    )


class _Index:
    def __init__(
        self,
        results: Mapping[str, AdapterFileResult],
        documents: Mapping[str, "_Document"],
    ) -> None:
        self.symbols = {
            e.id: e
            for result in results.values()
            for e in result.analysis.entities
            if isinstance(e, Symbol)
        }
        values = {
            e.id: e
            for result in results.values()
            for e in result.analysis.entities
            if isinstance(e, Value)
        }
        self.children: dict[str, dict[str, Symbol]] = defaultdict(dict)
        self.attributes: dict[str, dict[str, object]] = defaultdict(dict)
        self.refs = {}
        self.parent = {}
        self.path = {
            e.id: path
            for path, result in results.items()
            for e in result.analysis.entities
            if isinstance(e, Symbol)
        }
        self.documents = documents
        self.results = results
        self.by_pointer = {
            (path, _parts(e, path)): e
            for path, result in results.items()
            for e in result.analysis.entities
            if isinstance(e, Symbol)
        }
        for result in results.values():
            for e in result.analysis.entities:
                if not isinstance(e, Relation) or e.resolution.target is None:
                    continue
                target = e.resolution.target.id
                if e.relation_kind == RelationKind.CONTAINS and target in self.symbols:
                    self.children[e.source.id][self.symbols[target].name] = (
                        self.symbols[target]
                    )
                    self.parent[target] = e.source.id
                elif e.relation_kind == RelationKind.OPENAPI_ATTRIBUTE:
                    self.attributes[e.source.id][values[target].name] = values[
                        target
                    ].literal
                elif e.relation_kind == RelationKind.OPENAPI_REF:
                    self.refs[e.source.id] = target

    def child(self, symbol: Symbol | None, key: str) -> Symbol | None:
        return self.children[symbol.id].get(key) if symbol else None

    def value(self, symbol: Symbol | None, key: str) -> str | int | float | bool | None:
        if symbol is None:
            return None
        if key in self.attributes[symbol.id]:
            return self.attributes[symbol.id][key]
        child = self.child(symbol, key)
        return self.attributes[child.id].get(child.name) if child else None

    def resolve(self, symbol: Symbol | None) -> Symbol | None:
        seen = set()
        while symbol is not None and self.child(symbol, "$ref") is not None:
            if symbol.id in seen or len(seen) >= 32:
                return None
            seen.add(symbol.id)
            symbol = self.symbols.get(self.refs.get(symbol.id))
        return symbol

    def media(
        self, operation: Symbol, role: str
    ) -> tuple[set[str], tuple[Symbol, ...], bool]:
        nodes = []
        if role == "request":
            body = self.resolve(self.child(operation, "requestBody"))
            if body is not None:
                nodes.append(body)
            unknown = self.child(operation, "requestBody") is not None and body is None
        else:
            responses = self.resolve(self.child(operation, "responses"))
            statuses = self.children[responses.id] if responses else {}
            selected = [
                node for status, node in statuses.items() if status.startswith("2")
            ]
            if not selected and "default" in statuses:
                selected.append(statuses["default"])
            nodes = [
                resolved
                for node in selected
                if (resolved := self.resolve(node)) is not None
            ]
            unknown = len(nodes) != len(selected)
        media, schemas = set(), []
        for node in nodes:
            content = self.child(node, "content")
            if content is not None:
                for name, item in self.children[content.id].items():
                    media.add(name)
                    schema = self.resolve(self.child(item, "schema"))
                    if schema is not None and schema.symbol_kind in (
                        "OPENAPI_SCHEMA",
                        "OPENAPI_FIELD",
                    ):
                        schemas.append(schema)
        return media, tuple({s.id: s for s in schemas}.values()), unknown

    def parameters(self, operation: Symbol) -> tuple[tuple[Symbol, Symbol], ...]:
        path_item = self.symbols.get(self.parent.get(operation.id))
        if path_item and path_item.name == "additionalOperations":
            path_item = self.symbols.get(self.parent.get(path_item.id))
        effective = {}
        for owner in (path_item, operation):
            container = self.child(owner, "parameters")
            for child in self.children[container.id].values() if container else ():
                parameter = self.resolve(child)
                if parameter is not None:
                    name, kind = (
                        self.value(parameter, "name"),
                        self.value(parameter, "in"),
                    )
                    if isinstance(name, str) and isinstance(kind, str):
                        effective[kind, name.lower() if kind == "header" else name] = (
                            child,
                            parameter,
                        )
        return tuple(effective.values())

    def proof(self, symbol: Symbol, rule: str) -> Evidence:
        return Evidence(
            source_range=symbol.source_range,
            analyzer="openapi.java",
            analyzer_version=VERSION,
            rule=rule,
            description="Captured contract/configuration; runtime binding remains unproven.",
        )

    def servers(
        self, operation: Symbol
    ) -> tuple[tuple[tuple[str, str | None, tuple[Evidence, ...]], ...], bool]:
        owner = operation
        container = None
        while owner is not None:
            container = self.child(owner, "servers")
            if container is not None:
                break
            owner = self.symbols.get(self.parent.get(owner.id))
        if container is None or not self.children[container.id]:
            return (("", None, ()),), False
        result = []
        unknown = False
        for server in self.children[container.id].values():
            url = self.value(server, "url")
            if not isinstance(url, str):
                unknown = True
                continue
            try:
                uri = urlsplit(url)
                if (
                    uri.query
                    or uri.fragment
                    or "{" in url
                    or any(ord(c) < 32 for c in url)
                    or uri.scheme
                    and uri.scheme not in ("http", "https")
                    or not uri.scheme
                    and not uri.path.startswith("/")
                ):
                    raise ValueError("Unsupported/dynamic server context")
                result.append(
                    (
                        uri.path,
                        uri.netloc.rsplit("@", 1)[-1] or None,
                        (self.proof(server, "openapi.server"),),
                    )
                )
            except ValueError:
                unknown = True
        return tuple(result) or (("", None, ()),), unknown

    def contexts(self) -> tuple[tuple[tuple[str, tuple[Evidence, ...]], ...], bool]:
        found = []
        uncertain = any(
            posixpath.basename(path).startswith("application")
            and path not in self.documents
            for path in self.results
        )
        default_found = False
        for path, doc in self.documents.items():
            filename = posixpath.basename(path)
            if not filename.startswith("application") or not filename.endswith(
                (".yaml", ".yml", ".json")
            ):
                continue
            profiled = filename.split(".")[0] != "application"
            for parts in (
                ("server", "servlet", "context-path"),
                ("server.servlet.context-path",),
                ("spring", "webflux", "base-path"),
                ("spring.webflux.base-path",),
            ):
                if parts in doc.nodes:
                    uncertain |= profiled
                    default_found |= not profiled
                    value = doc.values.get(parts)
                    if (
                        not isinstance(value, str)
                        or route_key(value or "/")[0] is None
                        or "{" in value
                    ):
                        uncertain = True
                    else:
                        proof = Evidence(
                            source_range=doc.location(parts),
                            analyzer="openapi.java",
                            analyzer_version=VERSION,
                            rule="spring.application.context",
                            description="Captured application context; active runtime profiles are not inferred.",
                        )
                        found.append((value, (proof,)))
        if found and not default_found:
            found.append(("", ()))
        uncertain |= len({p for p, _ in found}) > 1
        return tuple(found) or (("", ()),), uncertain


def _mime(value: str) -> tuple[str, str, dict[str, str]] | None:
    parts = value.split(";")
    main = parts[0].strip().lower().split("/")
    if len(main) != 2 or any(not part or part.startswith("!") for part in main):
        return None
    parameters = {}
    for part in parts[1:]:
        key, sep, value = part.strip().partition("=")
        if not sep:
            return None
        key = key.lower()
        parameters[key] = (
            value.strip('"').lower() if key == "charset" else value.strip('"')
        )
    return main[0], main[1], parameters


def _media_match(
    declared: tuple[str, ...], contract: set[str], unknown: bool
) -> tuple[bool, bool]:
    if not declared:
        return True, False
    if not contract:
        return True, True
    uncertain = unknown
    found = False
    for raw in declared:
        left = _mime(raw)
        if left is None:
            uncertain = True
            found = True
            continue
        for value in contract:
            right = _mime(value)
            if right is None:
                uncertain = found = True
                continue
            type_match = left[0] == right[0] or "*" in (left[0], right[0])
            subtype = left[1] == right[1] or "*" in (left[1], right[1])
            subtype |= left[1].startswith("*+") and right[1].endswith(left[1][1:])
            subtype |= right[1].startswith("*+") and left[1].endswith(right[1][1:])
            if type_match and subtype:
                conflicts = any(
                    key in right[2] and right[2][key] != val
                    for key, val in left[2].items()
                )
                if not conflicts:
                    found = True
                    uncertain |= any(key not in right[2] for key in left[2])
    return found, uncertain


def _conditions(
    index: _Index, route: JavaHttpRoute, operation: Symbol
) -> tuple[bool, bool]:
    parameters = {
        (
            index.value(p, "in"),
            str(index.value(p, "name")).lower()
            if index.value(p, "in") == "header"
            else index.value(p, "name"),
        ): p
        for _, p in index.parameters(operation)
    }
    uncertain = False
    for kind, expressions in (("query", route.params), ("header", route.headers)):
        for expression in expressions:
            if "!=" in expression or expression.startswith("!"):
                uncertain = True
                continue
            key, sep, expected = expression.partition("=")
            key = key.lower() if kind == "header" else key
            parameter = parameters.get((kind, key))
            if parameter is None or index.value(parameter, "required") is not True:
                uncertain = True
                continue
            if sep:
                schema = index.resolve(index.child(parameter, "schema"))
                enum = index.child(schema, "enum")
                options = (
                    [index.value(schema, "const")]
                    if index.child(schema, "const")
                    else [
                        index.attributes[c.id].get(c.name)
                        for c in index.children[enum.id].values()
                    ]
                    if enum
                    else []
                )
                if options and expected not in options:
                    return False, False
                uncertain |= options != [expected]
    return True, uncertain


def bind_results(
    results: Mapping[str, AdapterFileResult],
    documents: Mapping[str, "_Document"],
    catalog: JavaHttpCatalog | None,
) -> dict[str, AdapterFileResult]:
    """Bind direct path operations to canonical Java handlers without remote lookup."""
    index = _Index(results, documents)
    contexts, uncertain_context = index.contexts()
    output = {}
    unenumerated = bool(
        catalog
        and (
            catalog.failed_paths
            or catalog.issues
            or any(
                r.kind == "SERVER"
                and (
                    route_key(r.path)[0] is None
                    or any(
                        "mapping" in reason.lower() and "inherited" in reason.lower()
                        for reason in r.incomplete
                    )
                )
                for r in catalog.routes
            )
        )
    )
    for path, result in results.items():
        if catalog is None or result.capabilities[0].status == "UNSUPPORTED":
            output[path] = AdapterFileResult(
                analysis=result.analysis,
                diagnostics=result.diagnostics,
                capabilities=(
                    *result.capabilities,
                    COVERAGE.model_copy(
                        update={
                            "status": "UNSUPPORTED",
                            "reasons": (
                                "Java route catalog unavailable or no active contract.",
                            ),
                        }
                    ),
                ),
            )
            continue
        facts = list(result.analysis.entities)
        diagnostics = list(result.diagnostics)

        def diagnostic(operation, code, message, diagnostics=diagnostics):
            diagnostics.append(
                SourceDiagnostic(
                    severity="WARNING",
                    code="openapi.java." + code,
                    message=message,
                    source_range=operation.source_range,
                )
            )

        def base(kind, operation, key, name):
            logical_key = operation.logical_key + ":" + VERSION + ":" + key
            return {
                "repository_id": operation.repository_id,
                "logical_key": logical_key,
                "id": logical_id(operation.repository_id, kind, logical_key),
                "name": name,
                "source_range": operation.source_range,
            }

        def ref(symbol):
            return EntityRef(id=symbol.id, entity_type=symbol.entity_type)

        def link(
            operation, origin, kind, targets, key, proof, partial=False, facts=facts
        ):
            refs = tuple(
                ref(item)
                for item in sorted(
                    {item.id: item for item in targets}.values(), key=lambda s: s.id
                )
            )
            status = (
                "AMBIGUOUS"
                if len(refs) > 1
                else "PARTIAL"
                if refs and partial
                else "RESOLVED"
                if refs
                else "UNRESOLVED"
            )
            resolution = (
                Resolution(status=status, target=refs[0])
                if status == "RESOLVED"
                else Resolution(
                    status=status,
                    candidates=refs,
                    reason="Incomplete/ambiguous captured route or signature constraints; runtime semantics are not proved.",
                )
            )
            facts.append(
                Relation(
                    **base(EntityType.RELATION, operation, key, kind.value),
                    relation_kind=kind,
                    source=ref(origin),
                    resolution=resolution,
                    certainty=Certainty.INFERRED if refs else Certainty.UNKNOWN,
                    evidence=tuple(dict.fromkeys(proof)),
                    coverage=COVERAGE,
                )
            )

        had_operation = False
        for operation in result.analysis.entities:
            if (
                not isinstance(operation, Symbol)
                or operation.symbol_kind != "OPENAPI_OPERATION"
            ):
                continue
            parts = _parts(operation, path)
            if parts[:1] != ("paths",) or len(parts) not in (3, 4):
                continue
            had_operation = True
            method, raw_path = (
                index.value(operation, "method"),
                index.value(operation, "path"),
            )
            proof = [index.proof(operation, "openapi.operation")]
            servers, unknown_server = index.servers(operation)
            effective = (
                [
                    (join_path(base_path, raw_path), service, p)
                    for base_path, service, p in servers
                ]
                if isinstance(raw_path, str)
                else []
            )
            request_media, request_schemas, request_unknown = index.media(
                operation, "request"
            )
            response_media, response_schemas, response_unknown = index.media(
                operation, "response"
            )
            matches = []
            matched_paths = set()
            node = documents[path].nodes.get(parts)
            supported = isinstance(node, MappingNode) and method in HTTP_METHODS
            for route in catalog.routes if supported else ():
                if (
                    route.kind != "SERVER"
                    or method not in (route.methods or HTTP_METHODS)
                    and not (method == "HEAD" and "GET" in route.methods)
                ):
                    continue
                consume, consume_partial = _media_match(
                    route.consumes, request_media, request_unknown
                )
                produce, produce_partial = _media_match(
                    route.produces, response_media, response_unknown
                )
                conditions, condition_partial = _conditions(index, route, operation)
                if not (consume and produce and conditions):
                    continue
                for mounted, mount_proof in contexts:
                    java_path = (
                        join_path(mounted, route.path)
                        if route.path is not None
                        else None
                    )
                    java_key, java_names, java_uncertain = route_key(java_path)
                    if java_key is None:
                        continue
                    for contract_path, _, server_proof in effective:
                        contract_key, contract_names, contract_uncertain = route_key(
                            contract_path
                        )
                        if java_key == contract_key:
                            matches.append(
                                (
                                    route,
                                    consume_partial
                                    or produce_partial
                                    or condition_partial
                                    or java_uncertain
                                    or contract_uncertain
                                    or bool(route.incomplete),
                                    dict(zip(contract_names, java_names)),
                                    (*server_proof, *mount_proof),
                                    contract_path,
                                )
                            )
                            matched_paths.add(contract_path)
            if method == "HEAD" and any(
                "HEAD" in route.methods for route, *_ in matches
            ):
                matches = [match for match in matches if "HEAD" in match[0].methods]
            matched_paths = {match[4] for match in matches}
            candidates = {route.symbol.id: route.symbol for route, *_ in matches}
            registrations = {
                route.registration.rsplit(":", 1)[0] for route, *_ in matches
            }
            partial = (
                unknown_server
                or uncertain_context
                or unenumerated
                or any(m[1] for m in matches)
                or len(registrations) > 1
                or len(matched_paths) != len({p for p, _, _ in effective})
            )
            for route, _, _, contextual_proof, _ in matches:
                proof.extend((*route.evidence, *contextual_proof))
            link(
                operation,
                operation,
                RelationKind.OPENAPI_HANDLER,
                tuple(candidates.values()),
                "handler",
                proof,
                partial,
            )
            if not candidates:
                diagnostic(
                    operation,
                    "UNRESOLVED_HANDLER",
                    "No compatible captured Spring route with proven method/path constraints.",
                )
                for ordinal, (effective_path, service, server_proof) in enumerate(
                    effective or [(str(raw_path), None, ())]
                ):
                    selector = (
                        HttpSelector(
                            method=method, path=effective_path, service=service
                        )
                        if method in HTTP_METHODS
                        and route_key(effective_path)[0] is not None
                        and not route_key(effective_path)[2]
                        and not unknown_server
                        else SymbolSelector(
                            qualified_name="openapi.http.dynamic::" + operation.id
                        )
                    )
                    facts.append(
                        ExternalReference(
                            **base(
                                EntityType.EXTERNAL_REFERENCE,
                                operation,
                                "handler.external:" + str(ordinal),
                                "HTTP implementation",
                            ),
                            source=ref(operation),
                            selector=selector,
                            reason="Local implementation missing or unsupported; target is deferred without reading another repository.",
                            evidence=(
                                index.proof(operation, "openapi.deferred-handler"),
                                *server_proof,
                            ),
                            certainty=Certainty.UNKNOWN,
                            coverage=COVERAGE,
                        )
                    )
            elif partial:
                diagnostic(
                    operation,
                    "PARTIAL_HANDLER",
                    "Candidate retained with incomplete route/configuration/catalog conditions.",
                )
            if len(candidates) > 1:
                diagnostic(
                    operation,
                    "AMBIGUOUS_HANDLER",
                    "Multiple compatible canonical Java handler methods.",
                )
            for schema_role, schemas, parameter_kind, relation_kind in (
                ("request", request_schemas, "body", RelationKind.OPENAPI_REQUEST_DTO),
                ("response", response_schemas, None, RelationKind.OPENAPI_RESPONSE_DTO),
            ):
                targets = []
                for route, *_ in matches:
                    targets.extend(
                        route.responses
                        if parameter_kind is None
                        else (
                            t
                            for p in route.parameters
                            if p.kind == parameter_kind
                            for t in p.types
                        )
                    )
                for schema in schemas:
                    if targets:
                        link(
                            operation,
                            schema,
                            relation_kind,
                            targets,
                            schema_role + ":" + schema.id,
                            (
                                *proof,
                                index.proof(
                                    schema, "contract.schema.signature-context"
                                ),
                                *(
                                    index.proof(t, "java.dto.declaration")
                                    for t in targets
                                ),
                            ),
                            True,
                        )
            for origin, parameter in index.parameters(operation):
                kind, name = (
                    index.value(parameter, "in"),
                    index.value(parameter, "name"),
                )
                targets = []
                parameter_proof = [*proof, index.proof(parameter, "contract.parameter")]
                for route, _, aliases, _, _ in matches:
                    expected = aliases.get(name, name) if kind == "path" else name
                    for java_parameter in route.parameters:
                        actual = java_parameter.name
                        if java_parameter.kind == kind and (
                            (actual.lower() == expected.lower())
                            if kind == "header"
                            and isinstance(actual, str)
                            and isinstance(expected, str)
                            else actual == expected
                        ):
                            targets.append(java_parameter.symbol)
                            parameter_proof.extend(java_parameter.evidence)
                if targets:
                    link(
                        operation,
                        origin,
                        RelationKind.OPENAPI_JAVA_PARAMETER,
                        targets,
                        "parameter:" + parameter.id,
                        parameter_proof,
                        True,
                    )
        dependencies = (
            tuple(
                sorted(
                    {
                        *result.analysis.dependencies,
                        *(f.path for f in catalog.source_files),
                        *(
                            p
                            for p in results
                            if posixpath.basename(p).startswith("application")
                        ),
                    }
                    - {path}
                )
            )
            if had_operation
            else result.analysis.dependencies
        )
        output[path] = AdapterFileResult(
            analysis=FileAnalysis(
                path=path, entities=tuple(facts), dependencies=dependencies
            ),
            diagnostics=tuple(diagnostics),
            capabilities=(*result.capabilities, COVERAGE),
        )
    return output
