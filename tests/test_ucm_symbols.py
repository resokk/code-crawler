import pytest
from pydantic import ValidationError

from code_crawler.ucm import (
    CallableSignature,
    EntityDocument,
    EntityType,
    Occurrence,
    Position,
    Scope,
    SourceRange,
    Symbol,
    TypeRef,
    callable_key,
    logical_id,
)


def envelope(kind: EntityType, key: str = "fixture") -> dict:
    return {
        "repository_id": "repo",
        "logical_key": key,
        "name": "m",
        "id": logical_id("repo", kind, key),
    }


def method(types: tuple[str, ...], owner: str = "A") -> Symbol:
    signature = CallableSignature(parameter_types=tuple(TypeRef(name=t) for t in types))
    key = callable_key(owner, "m", signature)
    return Symbol(
        **envelope(EntityType.SYMBOL, key),
        symbol_kind="METHOD",
        qualified_name=f"{owner}.m",
        owner_key=owner,
        signature=signature,
    )


def test_overloads_are_distinct_and_roundtrip() -> None:
    symbols = [
        method(()),
        method(("int",)),
        method(("String",)),
        method(("int", "String")),
        method(("String", "int")),
        method(("int",), "B"),
    ]
    assert len({s.id for s in symbols}) == len(symbols)
    assert method(("int",)).id == method(("int",)).id
    assert symbols[1].qualified_name == symbols[2].qualified_name
    for symbol in symbols:
        assert (
            EntityDocument.model_validate_json(symbol.model_dump_json()).root == symbol
        )


def test_return_type_and_resolution_do_not_change_identity() -> None:
    a = CallableSignature(parameter_types=(TypeRef(name="T"),))
    b = CallableSignature(
        parameter_types=(
            TypeRef(name="T", resolution="RESOLVED", target_symbol_id=method(()).id),
        ),
        return_type=TypeRef(name="void"),
    )
    assert callable_key("A", "m", a) == callable_key("A", "m", b)


@pytest.mark.parametrize(
    "changes",
    [
        {"signature": None},
        {"owner_key": None},
        {"signature": CallableSignature()},
        {"symbol_kind": "FIELD"},
    ],
)
def test_invalid_callable_is_rejected(changes: dict) -> None:
    with pytest.raises(ValidationError):
        Symbol.model_validate({**method(("int",)).model_dump(), **changes})


@pytest.mark.parametrize("kind", ["CLASS", "FIELD", "PARAMETER", "LOCAL_VARIABLE"])
def test_noncallable_roundtrip(kind: str) -> None:
    symbol = Symbol(
        **envelope(EntityType.SYMBOL),
        symbol_kind=kind,
        qualified_name="A.x",
        type_ref=TypeRef(name="int"),
    )
    assert EntityDocument.model_validate_json(symbol.model_dump_json()).root == symbol


def test_constructor_roundtrip() -> None:
    data = method(()).model_dump()
    data["symbol_kind"] = "CONSTRUCTOR"
    constructor = Symbol.model_validate(data)
    assert (
        EntityDocument.model_validate_json(constructor.model_dump_json()).root
        == constructor
    )


@pytest.mark.parametrize("kind", ["FILE", "TYPE", "CALLABLE", "BLOCK"])
def test_nested_scope_roundtrip(kind: str) -> None:
    parent = Scope(**envelope(EntityType.SCOPE, "parent"), scope_kind="FILE")
    child = Scope(
        **envelope(EntityType.SCOPE),
        scope_kind=kind,
        parent_scope_id=parent.id,
        owner_symbol_id=method(()).id,
    )
    assert EntityDocument.model_validate_json(child.model_dump_json()).root == child


def occurrence_data() -> dict:
    point = Position(line=1, byte_column=0)
    return dict(
        **envelope(EntityType.OCCURRENCE),
        scope_id=logical_id("repo", EntityType.SCOPE, "scope"),
        source_range=SourceRange(
            source_file_id=logical_id("repo", EntityType.SOURCE_FILE, "A.java"),
            start=point,
            end=point,
        ),
    )


@pytest.mark.parametrize("kind", ["DECLARATION", "REFERENCE", "READ", "WRITE", "CALL"])
@pytest.mark.parametrize("resolution", ["RESOLVED", "UNRESOLVED", "AMBIGUOUS"])
def test_occurrences_roundtrip(kind: str, resolution: str) -> None:
    occurrence = Occurrence(
        **occurrence_data(),
        occurrence_kind=kind,
        resolution=resolution,
        target_symbol_id=method(()).id if resolution == "RESOLVED" else None,
    )
    assert (
        EntityDocument.model_validate_json(occurrence.model_dump_json()).root
        == occurrence
    )


@pytest.mark.parametrize(
    "resolution,target",
    [("RESOLVED", None), ("UNRESOLVED", "target"), ("AMBIGUOUS", "target")],
)
def test_inconsistent_resolution_rejected(resolution: str, target: str | None) -> None:
    target_id = method(()).id if target else None
    with pytest.raises(ValidationError):
        TypeRef(name="T", resolution=resolution, target_symbol_id=target_id)
    with pytest.raises(ValidationError):
        Occurrence(
            **occurrence_data(),
            occurrence_kind="REFERENCE",
            resolution=resolution,
            target_symbol_id=target_id,
        )


def test_occurrence_requires_location_and_scope() -> None:
    with pytest.raises(ValidationError):
        Occurrence(**envelope(EntityType.OCCURRENCE), occurrence_kind="CALL")


@pytest.mark.parametrize("owner,name", [("", "m"), ("A", " ")])
def test_blank_callable_components_rejected(owner: str, name: str) -> None:
    with pytest.raises(ValueError):
        callable_key(owner, name, CallableSignature())
