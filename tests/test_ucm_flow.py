import pytest
from pydantic import ValidationError

from code_crawler.ucm import (
    EntityDocument,
    EntityType,
    Operation,
    TypeRef,
    Value,
    logical_id,
)


def envelope(kind: EntityType, key: str) -> dict:
    return {
        "repository_id": "repo",
        "logical_key": key,
        "id": logical_id("repo", kind, key),
        "name": key,
    }


def value_id(key: str) -> str:
    return logical_id("repo", EntityType.VALUE, key)


def operation(
    kind: str, inputs: tuple[str, ...], outputs: tuple[str, ...], **extra: object
) -> Operation:
    return Operation(
        **envelope(EntityType.OPERATION, kind),
        operation_kind=kind,
        scope_id=logical_id("repo", EntityType.SCOPE, "method"),
        input_value_ids=tuple(value_id(v) for v in inputs),
        output_value_ids=tuple(value_id(v) for v in outputs),
        **extra,
    )


@pytest.mark.parametrize(
    "literal", [None, "", "select * from users", 0, 42, 1.5, True, False]
)
def test_literal_roundtrip_preserves_scalar_type(literal: object) -> None:
    value = Value(
        **envelope(EntityType.VALUE, "literal"), value_kind="LITERAL", literal=literal
    )
    restored = EntityDocument.model_validate_json(value.model_dump_json()).root
    assert restored == value
    assert type(restored.literal) is type(literal)


@pytest.mark.parametrize(
    "kind,partial", [("UNKNOWN", True), ("SYMBOLIC", False), ("SYMBOLIC", True)]
)
def test_nonliteral_roundtrip(kind: str, partial: bool) -> None:
    value = Value(
        **envelope(EntityType.VALUE, "v"),
        value_kind=kind,
        partial=partial,
        type_ref=TypeRef(name="String"),
    )
    assert EntityDocument.model_validate_json(value.model_dump_json()).root == value


@pytest.mark.parametrize(
    "fields",
    [
        {"value_kind": "UNKNOWN"},
        {"value_kind": "UNKNOWN", "partial": True, "literal": "secret"},
        {"value_kind": "SYMBOLIC", "literal": 1},
        {"value_kind": "LITERAL", "partial": True},
        {"value_kind": "LITERAL", "literal": float("inf")},
        {"value_kind": "LITERAL", "literal": float("nan")},
        {"value_kind": "LITERAL", "literal": {}},
    ],
)
def test_invalid_values_rejected(fields: dict) -> None:
    with pytest.raises(ValidationError):
        Value(**envelope(EntityType.VALUE, "bad"), **fields)


@pytest.mark.parametrize(
    "kind,inputs,outputs",
    [
        ("READ", (), ("a",)),
        ("ASSIGN", ("a",), ("b",)),
        ("CONCAT", ("a", "a"), ("b",)),
        ("RETURN", (), ()),
        ("RETURN", ("a",), ()),
        ("CALL", (), ()),
        ("CALL", ("a", "b"), ("result",)),
    ],
)
def test_operations_roundtrip(
    kind: str, inputs: tuple[str, ...], outputs: tuple[str, ...]
) -> None:
    op = operation(kind, inputs, outputs)
    assert EntityDocument.model_validate_json(op.model_dump_json()).root == op


@pytest.mark.parametrize(
    "kind,inputs,outputs",
    [
        ("READ", ("a",), ("b",)),
        ("READ", (), ()),
        ("ASSIGN", (), ("b",)),
        ("ASSIGN", ("a",), ()),
        ("CONCAT", ("a",), ("b",)),
        ("RETURN", ("a", "b"), ()),
        ("RETURN", (), ("a",)),
        ("CALL", (), ("a", "b")),
        ("CALL", (), ("a", "a")),
        ("ASSIGN", ("a",), ("a",)),
    ],
)
def test_invalid_flow_cardinality_rejected(
    kind: str, inputs: tuple[str, ...], outputs: tuple[str, ...]
) -> None:
    with pytest.raises(ValidationError):
        operation(kind, inputs, outputs)


def test_callee_is_only_allowed_for_call() -> None:
    callee = TypeRef(name="p.Repository.run")
    call = operation("CALL", (), (), callee=callee)
    assert EntityDocument.model_validate_json(call.model_dump_json()).root == call
    with pytest.raises(ValidationError):
        operation("READ", (), ("a",), callee=callee)


def test_dataflow_chain_preserves_unknown_and_argument_order() -> None:
    values = [
        Value(
            **envelope(EntityType.VALUE, "prefix"),
            value_kind="LITERAL",
            literal="select * from users where name = ",
        ),
        Value(
            **envelope(EntityType.VALUE, "parameter"),
            value_kind="UNKNOWN",
            partial=True,
        ),
        Value(
            **envelope(EntityType.VALUE, "constructed"),
            value_kind="SYMBOLIC",
            partial=True,
        ),
        Value(
            **envelope(EntityType.VALUE, "assigned"),
            value_kind="SYMBOLIC",
            partial=True,
        ),
    ]
    concat = operation("CONCAT", ("prefix", "parameter"), ("constructed",))
    assign = operation("ASSIGN", ("constructed",), ("assigned",))
    call = operation("CALL", ("assigned",), (), callee=TypeRef(name="run"))
    documents = [
        EntityDocument.model_validate_json(v.model_dump_json()).root
        for v in [*values, concat, assign, call]
    ]
    assert documents == [*values, concat, assign, call]
    assert concat.output_value_ids == assign.input_value_ids
    assert assign.output_value_ids == call.input_value_ids
    assert concat.input_value_ids == (values[0].id, values[1].id)
    assert values[1].partial and values[2].partial and values[3].partial


def test_operation_requires_scope_and_rejects_malformed_value_ids() -> None:
    with pytest.raises(ValidationError):
        Operation(**envelope(EntityType.OPERATION, "call"), operation_kind="CALL")
    with pytest.raises(ValidationError):
        Operation(
            **envelope(EntityType.OPERATION, "call"),
            operation_kind="CALL",
            scope_id=logical_id("repo", EntityType.SCOPE, "scope"),
            input_value_ids=("bad",),
        )
