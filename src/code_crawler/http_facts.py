"""Typed Java HTTP declarations and deferred clients; central ingestion owns writes."""

from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.java_http_catalog import (
    HTTP_METHODS,
    VERSION,
    JavaHttpCatalog,
    JavaHttpRoute,
)
from code_crawler.ucm import (
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    ExternalReference,
    ExternalSelector,
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

HTTP_COVERAGE = Coverage(
    capability="java.http",
    analyzer_version=VERSION,
    status="PARTIAL",
    reasons=(
        "Declared Spring/Feign annotations only; runtime registration, serialization and deployment are not proved.",
    ),
)


def _ref(symbol: Symbol | Value) -> EntityRef:
    return EntityRef(id=symbol.id, entity_type=symbol.entity_type)


def client_selector(route: JavaHttpRoute, method: str) -> ExternalSelector:
    path = route.path
    if (
        path is not None
        and path.startswith("/")
        and not any(c in path for c in ("?", "#", "\0", "${"))
        and route.service
        and method in HTTP_METHODS
        and not any(
            "Feign" in reason or "RequestLine" in reason for reason in route.incomplete
        )
    ):
        return HttpSelector(method=method, path=path, service=route.service)
    return SymbolSelector(
        qualified_name=f"http.feign::{route.service or 'UNKNOWN'}::{method}::{path or 'UNKNOWN'}"
    )


def emit_java_http(
    source: SourceInput, analysis: FileAnalysis, catalog: JavaHttpCatalog
) -> tuple[FileAnalysis, tuple[SourceDiagnostic, ...]]:
    """Emit addressable route attributes, signature DTOs and unresolved Feign targets."""
    facts = list(analysis.entities)
    diagnostics = []
    routes = [
        route
        for route in catalog.routes
        if route.symbol.source_range.source_file_id == source.file.id
    ]

    def base(kind: EntityType, route: JavaHttpRoute, key: str, name: str) -> dict:
        logical_key = (
            route.symbol.logical_key
            + ":"
            + VERSION
            + ":"
            + route.registration
            + ":"
            + key
        )
        return {
            "repository_id": source.file.repository_id,
            "logical_key": logical_key,
            "id": logical_id(source.file.repository_id, kind, logical_key),
            "name": name,
            "source_range": route.symbol.source_range,
        }

    def dto(route, kind, targets, key, proof):
        if not targets:
            return
        targets = tuple({target.id: target for target in targets}.values())
        refs = tuple(_ref(t) for t in targets)
        facts.append(
            Relation(
                **base(EntityType.RELATION, route, key, kind.value),
                relation_kind=kind,
                source=_ref(route.symbol),
                resolution=Resolution(status="RESOLVED", target=refs[0])
                if len(refs) == 1
                else Resolution(
                    status="AMBIGUOUS",
                    candidates=refs,
                    reason="Multiple source definitions of a declared DTO type.",
                ),
                certainty=Certainty.INFERRED,
                evidence=tuple(dict.fromkeys(proof)),
                coverage=HTTP_COVERAGE,
            )
        )

    for route in routes:
        attributes = {
            "http.kind": (route.kind,),
            "http.path": (route.path,),
            "http.method": route.methods
            or (
                (None,)
                if route.kind == "CLIENT"
                or any("RequestMethod" in reason for reason in route.incomplete)
                else ("ANY",)
            ),
            "http.consumes": route.consumes,
            "http.produces": route.produces,
            "http.params": route.params,
            "http.headers": route.headers,
            "http.service": (route.service,) if route.kind == "CLIENT" else (),
        }
        for name, values in attributes.items():
            for ordinal, value in enumerate(values):
                item = Value(
                    **base(EntityType.VALUE, route, f"{name}:{ordinal}", name),
                    value_kind="LITERAL" if value is not None else "UNKNOWN",
                    literal=value,
                    partial=value is None,
                )
                facts.append(item)
                facts.append(
                    Relation(
                        **base(EntityType.RELATION, route, item.id, name),
                        relation_kind=RelationKind.HTTP_ATTRIBUTE,
                        source=_ref(route.symbol),
                        resolution=Resolution(status="RESOLVED", target=_ref(item)),
                        certainty=Certainty.INFERRED,
                        evidence=route.evidence,
                        coverage=HTTP_COVERAGE,
                    )
                )
        for parameter in route.parameters:
            if parameter.kind == "body":
                dto(
                    route,
                    RelationKind.HTTP_REQUEST_DTO,
                    parameter.types,
                    "request:" + parameter.symbol.id,
                    (*route.evidence, *parameter.evidence),
                )
        dto(
            route,
            RelationKind.HTTP_RESPONSE_DTO,
            route.responses,
            "response",
            route.evidence,
        )
        for reason in route.incomplete:
            diagnostics.append(
                SourceDiagnostic(
                    severity="WARNING",
                    code="java.http.PARTIAL_MAPPING",
                    message=reason,
                    source_range=route.symbol.source_range,
                )
            )
        if route.kind == "CLIENT":
            for method in route.methods or ("UNKNOWN",):
                facts.append(
                    ExternalReference(
                        **base(
                            EntityType.EXTERNAL_REFERENCE,
                            route,
                            "client:" + method,
                            "Feign " + method,
                        ),
                        source=_ref(route.symbol),
                        selector=client_selector(route, method),
                        reason="Declared Feign request; runtime execution and remote target are deferred.",
                        certainty=Certainty.UNKNOWN,
                        evidence=route.evidence,
                        coverage=HTTP_COVERAGE,
                    )
                )
    for issue in catalog.issues:
        if issue.evidence.source_range.source_file_id == source.file.id:
            diagnostics.append(
                SourceDiagnostic(
                    severity="WARNING",
                    code="java.http." + issue.code,
                    message=issue.message,
                    source_range=issue.evidence.source_range,
                )
            )
    dependencies = (
        tuple(
            sorted(
                {
                    *analysis.dependencies,
                    *(
                        f.path
                        for f in catalog.source_files
                        if f.path != source.file.path
                    ),
                }
            )
        )
        if routes
        else analysis.dependencies
    )
    return FileAnalysis(
        path=analysis.path, entities=tuple(facts), dependencies=dependencies
    ), tuple(diagnostics)
