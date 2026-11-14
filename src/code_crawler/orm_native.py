"""Confirmed native-query strings reuse canonical SQL construction/semantic facts."""

import json

from tree_sitter import Node

from code_crawler import java
from code_crawler.java_calls import _File
from code_crawler.java_semantic import _envelope, _relation, semantic_constructions
from code_crawler.ucm import (
    CodeEntity,
    Coverage,
    Entity,
    EntityRef,
    EntityType,
    Evidence,
    Resolution,
    SourceRange,
    SqlConstruction,
    SqlFragment,
    SqlStatement,
    SqlVariant,
    Symbol,
)


def native_facts(
    file: _File,
    owner: Symbol,
    value: java._Value | None,
    node: Node | None,
    base: tuple[Entity, ...],
    coverage: Coverage,
    semantic_coverage: Coverage,
    dialect: str,
) -> tuple[tuple[Entity, ...], SqlConstruction | None, tuple[SqlStatement, ...]]:
    """Recover even native SELECT literals outside the discovery heuristic."""
    if node is None or value is None or not value.text.strip():
        return (), None, ()
    location = file.result._extractor.range(node)
    construction = next(
        (
            e
            for e in base
            if isinstance(e, SqlConstruction)
            and e.owner_symbol_id == owner.id
            and e.source_range == location
            and any(v.text == value.text.strip() for v in e.variants)
        ),
        None,
    )
    if construction:
        ids = {v.candidate_id for v in construction.variants}
        return (
            (),
            construction,
            tuple(
                e for e in base if isinstance(e, SqlStatement) and e.candidate_id in ids
            ),
        )
    key = json.dumps(
        [
            "java.sql",
            owner.logical_key,
            file.source.file.path,
            node.start_byte,
            node.end_byte,
        ],
        separators=(",", ":"),
    )
    candidate_key = key + ":candidate:0"
    candidate = CodeEntity(
        **_envelope(
            owner.repository_id,
            EntityType.SQL_CANDIDATE,
            candidate_key,
            "Native SQL",
            location,
        ),
        entity_type=EntityType.SQL_CANDIDATE,
    )
    reasons = value.reasons or (
        ("partial native SQL recovery",) if value.partial else ()
    )
    fragments = java._trim_fragments(value)
    if any(f.dynamic for f in fragments) and not reasons:
        reasons = ("dynamic native SQL fragment",)
    variant = SqlVariant(
        candidate_id=candidate.id,
        text=value.text.strip(),
        partial=bool(reasons),
        partial_reasons=reasons,
        fragments=tuple(
            SqlFragment(
                kind="DYNAMIC" if f.dynamic else "STATIC",
                text=f.text,
                source_range=SourceRange(
                    source_file_id=file.source.file.id,
                    start=f.source_span.start,
                    end=f.source_span.end,
                )
                if f.source_span
                else None,
            )
            for f in fragments
        ),
    )
    construction = SqlConstruction(
        **_envelope(
            owner.repository_id,
            EntityType.SQL_CONSTRUCTION,
            key,
            "Native SQL construction",
            location,
        ),
        owner_symbol_id=owner.id,
        variants=(variant,),
    )
    evidence = Evidence(
        source_range=location,
        analyzer="jpa.orm",
        analyzer_version="1",
        rule="native-query-construction",
        description="Explicit native SQL query argument; creation alone is not execution",
    )
    entities = [candidate, construction]
    for kind, source, target in (
        (
            "CONSTRUCTS_SQL",
            EntityRef(id=owner.id, entity_type=EntityType.SYMBOL),
            EntityRef(id=construction.id, entity_type=EntityType.SQL_CONSTRUCTION),
        ),
        (
            "HAS_SQL_CANDIDATE",
            EntityRef(id=construction.id, entity_type=EntityType.SQL_CONSTRUCTION),
            EntityRef(id=candidate.id, entity_type=EntityType.SQL_CANDIDATE),
        ),
    ):
        from code_crawler.ucm import RelationKind

        entities.append(
            _relation(
                owner.repository_id,
                key + ":" + kind,
                RelationKind(kind),
                source,
                Resolution(status="RESOLVED", target=target),
                evidence,
                coverage,
            )
        )
    facts, statements = semantic_constructions(
        {construction.id: construction}, owner.repository_id, dialect, semantic_coverage
    )
    entities.extend(facts)
    return tuple(entities), construction, tuple(statements[construction.id])
