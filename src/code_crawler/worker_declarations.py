"""Persist explicit D02 worker registrations independently of BPMN references."""

import json

from code_crawler.bpmn_java_catalog import JavaBindingCatalog, JavaHandler
from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.ucm import (
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    Relation,
    RelationKind,
    Resolution,
    Symbol,
    Value,
    logical_id,
)

VERSION = "bpmn.worker/1"
COVERAGE = Coverage(
    capability="bpmn.worker.declarations",
    analyzer_version=VERSION,
    status="PARTIAL",
    reasons=("Static handler registration; deployment and activation are not proven.",),
)


def emit_workers(
    source: SourceInput, analysis: FileAnalysis, catalog: JavaBindingCatalog | None
) -> FileAnalysis:
    """Use only supported D02 declarations, never task references or bean similarity."""
    if catalog is None:
        return analysis
    entities = list(analysis.entities)
    seen = set()
    for handler in catalog.handlers:
        location = handler.evidence[0].source_range
        identity = (
            handler.registration,
            handler.engine,
            handler.selector,
            handler.symbol.id,
        )
        if (
            handler.kind != "WORKER"
            or any(token in handler.selector for token in ("${", "#{", "<unknown>"))
            or location.source_file_id != source.file.id
            or identity in seen
        ):
            continue
        seen.add(identity)
        entities.extend(_emit_worker(source, handler, identity))
    return analysis.model_copy(update={"entities": tuple(entities)})


def _emit_worker(source: SourceInput, handler: JavaHandler, identity: tuple) -> tuple:
    entities = []
    location = handler.evidence[0].source_range
    key = VERSION + ":" + json.dumps(identity, separators=(",", ":"))

    def base(kind: EntityType, suffix: str) -> dict:
        logical_key = key + suffix
        return {
            "repository_id": source.file.repository_id,
            "logical_key": logical_key,
            "id": logical_id(source.file.repository_id, kind, logical_key),
            "source_range": location,
        }

    worker = Symbol(
        **base(EntityType.SYMBOL, ""),
        name=handler.selector,
        symbol_kind="BPMN_WORKER",
        qualified_name="bpmn.worker::"
        + json.dumps([handler.engine, handler.selector], separators=(",", ":")),
    )
    entities.append(worker)

    def link(kind: RelationKind, target: Symbol | Value, suffix: str) -> None:
        entities.append(
            Relation(
                **base(EntityType.RELATION, suffix),
                name=kind.value,
                relation_kind=kind,
                source=EntityRef(entity_type=EntityType.SYMBOL, id=worker.id),
                resolution=Resolution(
                    status="RESOLVED",
                    target=EntityRef(entity_type=target.entity_type, id=target.id),
                ),
                certainty=Certainty.INFERRED,
                coverage=COVERAGE,
                evidence=handler.evidence,
            )
        )

    link(RelationKind.BPMN_WORKER_HANDLER, handler.symbol, ":handler")
    for name, literal in (
        ("engine", handler.engine),
        ("worker_type", handler.selector),
    ):
        value = Value(
            **base(EntityType.VALUE, ":" + name),
            name=name,
            value_kind="LITERAL",
            literal=literal,
        )
        entities.append(value)
        link(RelationKind.BPMN_ATTRIBUTE, value, ":attribute:" + name)
    return tuple(entities)
