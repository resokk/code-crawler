import hashlib

import pytest
from pydantic import ValidationError

from code_crawler.ucm import (
    Certainty,
    CodeEntity,
    Coverage,
    EntityDocument,
    EntityRef,
    EntityType,
    Evidence,
    Occurrence,
    Operation,
    Position,
    Relation,
    RelationKind,
    Resolution,
    SourceFile,
    SourceRange,
    Symbol,
    logical_id,
    relation_registry,
    validate_relation_endpoints,
)


def envelope(kind: EntityType, key: str, repository: str = "repo") -> dict:
    return {
        "repository_id": repository,
        "logical_key": key,
        "name": key,
        "id": logical_id(repository, kind, key),
    }


def ref(kind: EntityType, key: str = "target") -> EntityRef:
    return EntityRef(id=logical_id("repo", kind, key), entity_type=kind)


def file(repository: str = "repo") -> SourceFile:
    return SourceFile(
        **envelope(EntityType.SOURCE_FILE, "A.java", repository),
        path="A.java",
        language="java",
        content_sha256=hashlib.sha256(b"class A {}").hexdigest(),
    )


def evidence() -> Evidence:
    point = Position(line=1, byte_column=0)
    return Evidence(
        source_range=SourceRange(source_file_id=file().id, start=point, end=point),
        analyzer="java",
        analyzer_version="1",
        rule="ast.call",
        description="Static call site",
    )


def coverage(status: str = "COMPLETE") -> Coverage:
    return Coverage(
        capability="java.calls",
        analyzer_version="1",
        status=status,
        reasons=() if status == "COMPLETE" else ("dynamic dispatch",),
    )


def relation(
    kind: RelationKind = RelationKind.CALLS,
    source: EntityRef | None = None,
    resolution: Resolution | None = None,
    **changes: object,
) -> Relation:
    data = dict(
        **envelope(EntityType.RELATION, "callsite"),
        relation_kind=kind,
        source=source or ref(EntityType.METHOD, "source"),
        resolution=resolution
        or Resolution(status="RESOLVED", target=ref(EntityType.METHOD)),
        certainty=Certainty.STATIC_PROVEN,
        evidence=(evidence(),),
        coverage=coverage(),
    )
    data.update(changes)
    return Relation(**data)


PAIRS = [
    (kind, source, target)
    for kind, pairs in relation_registry().items()
    for source, target in pairs
]


@pytest.mark.parametrize("kind,source,target", PAIRS)
def test_registry_pairs_roundtrip(
    kind: RelationKind, source: EntityType, target: EntityType
) -> None:
    fact = relation(
        kind, ref(source, "source"), Resolution(status="RESOLVED", target=ref(target))
    )
    assert EntityDocument.model_validate_json(fact.model_dump_json()).root == fact


@pytest.mark.parametrize("kind", list(RelationKind))
def test_registry_rejects_wrong_source_and_target(kind: RelationKind) -> None:
    source, _ = next(iter(relation_registry()[kind]))
    with pytest.raises(ValidationError):
        relation(kind, ref(EntityType.RELATION))
    with pytest.raises(ValidationError):
        relation(
            kind,
            ref(source),
            Resolution(status="RESOLVED", target=ref(EntityType.SOURCE_FILE)),
        )


def test_registry_is_complete_and_immutable() -> None:
    registry = relation_registry()
    assert set(registry) == set(RelationKind)
    with pytest.raises(TypeError):
        registry[RelationKind.CALLS] = frozenset()


@pytest.mark.parametrize(
    "status,count", [("UNRESOLVED", 0), ("PARTIAL", 1), ("AMBIGUOUS", 2)]
)
def test_unresolved_relations_preserve_candidates(status: str, count: int) -> None:
    result = Resolution(
        status=status,
        reason="not enough context",
        candidates=tuple(ref(EntityType.METHOD, str(i)) for i in range(count)),
    )
    fact = relation(
        resolution=result, certainty=Certainty.UNKNOWN, coverage=coverage("PARTIAL")
    )
    assert EntityDocument.model_validate_json(fact.model_dump_json()).root == fact
    assert fact.resolution.target is None
    with pytest.raises(ValidationError):
        relation(resolution=result)


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "RESOLVED"},
        {
            "status": "RESOLVED",
            "target": ref(EntityType.METHOD),
            "candidates": (ref(EntityType.METHOD),),
        },
        {"status": "UNRESOLVED"},
        {"status": "UNRESOLVED", "reason": "x", "target": ref(EntityType.METHOD)},
        {
            "status": "UNRESOLVED",
            "reason": "x",
            "candidates": (ref(EntityType.METHOD),),
        },
        {"status": "PARTIAL", "reason": "x"},
        {"status": "AMBIGUOUS", "reason": "x", "candidates": (ref(EntityType.METHOD),)},
        {
            "status": "AMBIGUOUS",
            "reason": "x",
            "candidates": (ref(EntityType.METHOD), ref(EntityType.METHOD)),
        },
        {"status": "UNRESOLVED", "reason": " "},
    ],
)
def test_invalid_resolution_rejected(fields: dict) -> None:
    with pytest.raises(ValidationError):
        Resolution(**fields)


def test_candidates_are_checked_against_registry() -> None:
    with pytest.raises(ValidationError):
        relation(
            resolution=Resolution(
                status="PARTIAL", reason="unknown", candidates=(ref(EntityType.VALUE),)
            ),
            certainty=Certainty.INFERRED,
        )


@pytest.mark.parametrize(
    "status,reasons",
    [
        ("COMPLETE", ("error",)),
        ("PARTIAL", ()),
        ("UNSUPPORTED", ()),
        ("PARTIAL", (" ",)),
    ],
)
def test_invalid_coverage_rejected(status: str, reasons: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        Coverage(
            capability="java.calls",
            analyzer_version="1",
            status=status,
            reasons=reasons,
        )


def test_unsupported_does_not_assert_confirmed_fact() -> None:
    fact = relation(
        resolution=Resolution(status="UNRESOLVED", reason="unsupported"),
        certainty=Certainty.UNKNOWN,
        coverage=coverage("UNSUPPORTED"),
    )
    assert EntityDocument.model_validate_json(fact.model_dump_json()).root == fact
    with pytest.raises(ValidationError):
        relation(coverage=coverage("UNSUPPORTED"))
    with pytest.raises(ValidationError):
        relation(
            resolution=fact.resolution,
            certainty=Certainty.INFERRED,
            coverage=fact.coverage,
        )


def test_evidence_is_mandatory_and_typed() -> None:
    with pytest.raises(ValidationError):
        relation(evidence=())
    with pytest.raises(ValidationError):
        Evidence.model_validate({**evidence().model_dump(), "rule": " "})
    with pytest.raises(ValidationError):
        Evidence.model_validate({**evidence().model_dump(), "source_range": None})


def catalog() -> dict:
    source = CodeEntity(
        **envelope(EntityType.METHOD, "source"), entity_type=EntityType.METHOD
    )
    target = CodeEntity(
        **envelope(EntityType.METHOD, "target"), entity_type=EntityType.METHOD
    )
    return {entity.id: entity for entity in (source, target, file())}


def test_actual_endpoints_and_recursive_calls() -> None:
    entities = catalog()
    fact = relation()
    validate_relation_endpoints(fact, entities)
    recursive = relation(resolution=Resolution(status="RESOLVED", target=fact.source))
    validate_relation_endpoints(recursive, entities)
    inferred = relation(certainty=Certainty.INFERRED)
    assert inferred.certainty == Certainty.INFERRED


@pytest.mark.parametrize(
    "problem",
    [
        "missing_source",
        "missing_target",
        "wrong_type",
        "foreign_repo",
        "missing_file",
        "foreign_file",
    ],
)
def test_actual_catalog_mismatches_rejected(problem: str) -> None:
    entities = catalog()
    fact = relation()
    if problem == "missing_source":
        entities.pop(fact.source.id)
    elif problem == "missing_target":
        entities.pop(fact.resolution.target.id)
    elif problem == "wrong_type":
        entities[fact.source.id] = file()
    elif problem == "foreign_repo":
        other = CodeEntity(
            **envelope(EntityType.METHOD, "target", "other"),
            entity_type=EntityType.METHOD,
        )
        fact = relation(
            resolution=Resolution(
                status="RESOLVED",
                target=EntityRef(id=other.id, entity_type=EntityType.METHOD),
            )
        )
        entities[other.id] = other
    elif problem == "missing_file":
        entities.pop(file().id)
    else:
        other = file("other")
        ev = Evidence.model_validate(
            {
                **evidence().model_dump(),
                "source_range": {
                    **evidence().source_range.model_dump(),
                    "source_file_id": other.id,
                },
            }
        )
        fact = relation(evidence=(ev,))
        entities[other.id] = other
    with pytest.raises(ValueError):
        validate_relation_endpoints(fact, entities)


def test_candidates_must_exist_in_catalog() -> None:
    fact = relation(
        resolution=Resolution(
            status="PARTIAL",
            reason="context",
            candidates=(ref(EntityType.METHOD, "absent"),),
        ),
        certainty=Certainty.UNKNOWN,
    )
    with pytest.raises(ValueError):
        validate_relation_endpoints(fact, catalog())


def test_call_and_declaration_subtypes_are_checked() -> None:
    entities = catalog()
    field = Symbol(
        **envelope(EntityType.SYMBOL, "field"),
        symbol_kind="FIELD",
        qualified_name="A.field",
    )
    entities[field.id] = field
    with pytest.raises(ValueError):
        validate_relation_endpoints(
            relation(source=EntityRef(id=field.id, entity_type=EntityType.SYMBOL)),
            entities,
        )
    op = Operation(
        **envelope(EntityType.OPERATION, "return"),
        operation_kind="RETURN",
        scope_id=ref(EntityType.SCOPE).id,
    )
    entities[op.id] = op
    with pytest.raises(ValueError):
        validate_relation_endpoints(
            relation(source=EntityRef(id=op.id, entity_type=EntityType.OPERATION)),
            entities,
        )
    occurrence = Occurrence(
        **envelope(EntityType.OCCURRENCE, "ref"),
        occurrence_kind="REFERENCE",
        source_range=evidence().source_range,
        scope_id=ref(EntityType.SCOPE).id,
    )
    entities[occurrence.id] = occurrence
    fact = relation(
        RelationKind.DECLARES,
        EntityRef(id=occurrence.id, entity_type=EntityType.OCCURRENCE),
    )
    with pytest.raises(ValueError):
        validate_relation_endpoints(fact, entities)
    declaration = Occurrence.model_validate(
        {**occurrence.model_dump(), "occurrence_kind": "DECLARATION"}
    )
    entities[declaration.id] = declaration
    validate_relation_endpoints(fact, entities)
