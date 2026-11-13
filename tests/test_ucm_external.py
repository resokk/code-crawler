import pytest
from pydantic import ValidationError

from code_crawler.ucm import (
    Certainty,
    CodeEntity,
    Coverage,
    DatabaseSelector,
    EntityDocument,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    HttpSelector,
    Position,
    Relation,
    RelationKind,
    Resolution,
    SourceFile,
    SourceRange,
    SymbolSelector,
    logical_id,
    validate_external_reference,
    validate_relation_endpoints,
)


def envelope(kind: EntityType, key: str, repository: str = "repo") -> dict:
    return {
        "repository_id": repository,
        "logical_key": key,
        "name": key,
        "id": logical_id(repository, kind, key),
    }


def source() -> CodeEntity:
    return CodeEntity(
        **envelope(EntityType.METHOD, "A.m"), entity_type=EntityType.METHOD
    )


def file(repository: str = "repo") -> SourceFile:
    return SourceFile(
        **envelope(EntityType.SOURCE_FILE, "A.java", repository),
        path="A.java",
        language="java",
        content_sha256="a" * 64,
    )


def reference(selector: object | None = None, **changes: object) -> ExternalReference:
    point = Position(line=1, byte_column=0)
    ev = Evidence(
        source_range=SourceRange(source_file_id=file().id, start=point, end=point),
        analyzer="java",
        analyzer_version="1",
        rule="external-call",
        description="Static dependency",
    )
    fields = {
        **envelope(EntityType.EXTERNAL_REFERENCE, "callsite:1"),
        "source": EntityRef(id=source().id, entity_type=source().entity_type),
        "selector": selector or SymbolSelector(qualified_name="lib.Client.send"),
        "reason": "target not available locally",
        "evidence": (ev,),
        "certainty": Certainty.INFERRED,
        "coverage": Coverage(
            capability="java.external", analyzer_version="1", status="COMPLETE"
        ),
    }
    fields.update(changes)
    return ExternalReference(**fields)


@pytest.mark.parametrize(
    "selector",
    [
        SymbolSelector(qualified_name="lib.Client.send"),
        SymbolSelector(qualified_name="lib.Client.send", parameter_type_names=()),
        SymbolSelector(
            qualified_name="lib.Client.send", parameter_type_names=("String", "int")
        ),
        HttpSelector(method="GET", path="/users/{id}", service="users"),
        DatabaseSelector(connection="billing", schema_name="Public", table="Users"),
    ],
)
def test_selector_roundtrip_without_external_index(selector: object) -> None:
    external = reference(selector, repository_hint="service-repo", version_hint="v2")
    restored = EntityDocument.model_validate_json(external.model_dump_json()).root
    assert restored == external
    assert restored.resolution == "UNRESOLVED"
    validate_external_reference(
        restored, {entity.id: entity for entity in (source(), file())}
    )


def test_unknown_signature_differs_from_zero_parameters() -> None:
    unknown = reference(SymbolSelector(qualified_name="A.m"))
    empty = reference(SymbolSelector(qualified_name="A.m", parameter_type_names=()))
    assert unknown.selector.parameter_type_names is None
    assert empty.selector.parameter_type_names == ()
    assert unknown.id == empty.id


def test_identity_is_local_callsite_not_global_selector() -> None:
    first = reference()
    another = reference(**envelope(EntityType.EXTERNAL_REFERENCE, "callsite:2"))
    foreign = reference(
        **envelope(EntityType.EXTERNAL_REFERENCE, "callsite:1", "other")
    )
    assert first.selector == another.selector == foreign.selector
    assert len({first.id, another.id, foreign.id}) == 3
    assert reference(version_hint="new").id == first.id


@pytest.mark.parametrize(
    "fields",
    [
        {"resolution": "RESOLVED"},
        {"resolution": "PARTIAL"},
        {"target": EntityRef(id=source().id, entity_type=EntityType.METHOD)},
        {"candidates": ()},
        {"reason": " "},
        {"evidence": ()},
        {"repository_hint": " "},
        {"version_hint": ""},
        {"source": EntityRef(id=file().id, entity_type=EntityType.SOURCE_FILE)},
        {"selector": {"kind": "UNKNOWN", "name": "x"}},
    ],
)
def test_invalid_external_contract_rejected(fields: dict) -> None:
    with pytest.raises(ValidationError):
        reference(**fields)


@pytest.mark.parametrize(
    "fields",
    [
        {"method": "get", "path": "/users"},
        {"method": "GET", "path": "users"},
        {"method": "GET", "path": "/users?q=x"},
        {"method": "GET", "path": "/users#fragment"},
    ],
)
def test_invalid_http_selector_rejected(fields: dict) -> None:
    with pytest.raises(ValidationError):
        HttpSelector(**fields)


@pytest.mark.parametrize(
    "selector",
    [
        {"kind": "SYMBOL", "qualified_name": " "},
        {"kind": "SYMBOL", "qualified_name": "A.m", "parameter_type_names": ("",)},
        {"kind": "DATABASE", "connection": " ", "table": "users"},
        {"kind": "DATABASE", "connection": "main", "table": " "},
    ],
)
def test_blank_selectors_rejected(selector: dict) -> None:
    with pytest.raises(ValidationError):
        reference(selector)


def test_unsupported_requires_unknown_certainty() -> None:
    coverage = Coverage(
        capability="java.external",
        analyzer_version="1",
        status="UNSUPPORTED",
        reasons=("unsupported syntax",),
    )
    with pytest.raises(ValidationError):
        reference(coverage=coverage)
    external = reference(coverage=coverage, certainty=Certainty.UNKNOWN)
    assert (
        EntityDocument.model_validate_json(external.model_dump_json()).root == external
    )


@pytest.mark.parametrize(
    "problem",
    ["missing_source", "wrong_type", "foreign_source", "missing_file", "foreign_file"],
)
def test_local_catalog_validation(problem: str) -> None:
    external = reference()
    entities = {entity.id: entity for entity in (source(), file())}
    if problem == "missing_source":
        entities.pop(source().id)
    elif problem == "wrong_type":
        entities[source().id] = file()
    elif problem == "foreign_source":
        other = CodeEntity(
            **envelope(EntityType.METHOD, "B.m", "other"), entity_type=EntityType.METHOD
        )
        entities[other.id] = other
        external = reference(
            source=EntityRef(id=other.id, entity_type=EntityType.METHOD)
        )
    elif problem == "missing_file":
        entities.pop(file().id)
    else:
        other = file("other")
        entities[other.id] = other
        ev = external.evidence[0]
        changed = Evidence.model_validate(
            {
                **ev.model_dump(),
                "source_range": {
                    **ev.source_range.model_dump(),
                    "source_file_id": other.id,
                },
            }
        )
        external = reference(evidence=(changed,))
    with pytest.raises(ValueError):
        validate_external_reference(external, entities)


def test_local_external_dependency_is_not_a_resolved_external_call() -> None:
    external = reference()
    relation = Relation(
        **envelope(EntityType.RELATION, "external-link"),
        relation_kind=RelationKind.EXTERNAL_DEPENDENCY,
        source=external.source,
        resolution=Resolution(
            status="RESOLVED",
            target=EntityRef(id=external.id, entity_type=external.entity_type),
        ),
        certainty=Certainty.STATIC_PROVEN,
        evidence=external.evidence,
        coverage=external.coverage,
    )
    entities = {entity.id: entity for entity in (source(), file(), external)}
    validate_relation_endpoints(relation, entities)
    assert (
        EntityDocument.model_validate_json(relation.model_dump_json()).root == relation
    )
    assert external.resolution == "UNRESOLVED"
    with pytest.raises(ValidationError):
        Relation.model_validate(
            {**relation.model_dump(), "relation_kind": RelationKind.CALLS}
        )
