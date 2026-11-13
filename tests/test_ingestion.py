from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from code_crawler.ingestion import UcmBatch
from code_crawler.ucm import (
    EntityType,
    Operation,
    Scope,
    TypeRef,
    Value,
    logical_id,
)


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate",
        "missing_file",
        "missing_scope",
        "wrong_type",
        "foreign_repo",
        "multiple_producers",
        "scope_cycle",
        "missing_typeref",
    ],
)
def test_invalid_closed_batches_rejected(
    ucm_batch_factory: Callable[[UUID], UcmBatch], problem: str
) -> None:
    batch = ucm_batch_factory(uuid4())
    entities = list(batch.entities)
    if problem == "duplicate":
        entities.append(entities[0])
    elif problem == "missing_file":
        entities = [e for e in entities if e.entity_type != EntityType.SOURCE_FILE]
    elif problem == "missing_scope":
        entities = [e for e in entities if not isinstance(e, Scope)]
    elif problem == "wrong_type":
        index = next(i for i, e in enumerate(entities) if isinstance(e, Operation))
        value = next(e for e in entities if isinstance(e, Scope))
        entities[index] = Operation.model_validate(
            {**entities[index].model_dump(), "input_value_ids": (value.id,)}
        )
    elif problem == "foreign_repo":
        with pytest.raises(ValidationError):
            UcmBatch(repository_id=uuid4(), entities=tuple(entities))
        return
    elif problem == "multiple_producers":
        operation = next(e for e in entities if isinstance(e, Operation))
        entities.append(
            Operation.model_validate(
                {
                    **operation.model_dump(),
                    "logical_key": "second",
                    "id": logical_id(
                        str(batch.repository_id), EntityType.OPERATION, "second"
                    ),
                }
            )
        )
    elif problem == "scope_cycle":
        index = next(i for i, e in enumerate(entities) if isinstance(e, Scope))
        entities[index] = Scope.model_validate(
            {**entities[index].model_dump(), "parent_scope_id": entities[index].id}
        )
    else:
        index = next(i for i, e in enumerate(entities) if isinstance(e, Value))
        entities[index] = Value.model_validate(
            {
                **entities[index].model_dump(),
                "type_ref": TypeRef(
                    name="missing",
                    resolution="RESOLVED",
                    target_symbol_id=logical_id(
                        str(batch.repository_id), EntityType.SYMBOL, "absent"
                    ),
                ),
            }
        )
    with pytest.raises(ValidationError):
        UcmBatch(repository_id=batch.repository_id, entities=tuple(entities))


def test_batch_roundtrip_and_empty_batch(
    ucm_batch_factory: Callable[[UUID], UcmBatch],
) -> None:
    batch = ucm_batch_factory(uuid4())
    assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
    assert UcmBatch(repository_id=uuid4(), entities=()).entities == ()
