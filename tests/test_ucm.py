import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from code_crawler.ucm import (
    CodeEntity,
    EntityDocument,
    EntityType,
    Position,
    SourceFile,
    SourceRange,
    entity_json_schema,
    logical_id,
)


def source_file(path: str = "src/Пример.java") -> SourceFile:
    return SourceFile(
        repository_id="repo:one",
        logical_key=path,
        id=logical_id("repo:one", EntityType.SOURCE_FILE, path),
        name="Пример.java",
        path=path,
        language="java",
        content_sha256=hashlib.sha256(b"class A {}").hexdigest(),
    )


def test_identity_has_fixed_canonical_encoding_and_scope() -> None:
    payload = '["ucm",1,"repo:one","CLASS","пакет.A"]'.encode()
    expected = "ucm:" + hashlib.sha256(payload).hexdigest()
    assert logical_id("repo:one", EntityType.CLASS, "пакет.A") == expected
    assert logical_id("repo:two", EntityType.CLASS, "пакет.A") != expected
    assert logical_id("repo:one", EntityType.METHOD, "пакет.A") != expected
    assert logical_id("repo:one", EntityType.CLASS, "пакет.B") != expected


def test_source_file_roundtrip_and_content_independent_identity() -> None:
    file = source_file()
    restored = EntityDocument.model_validate_json(file.model_dump_json()).root
    assert restored == file
    changed = SourceFile.model_validate(
        {
            **file.model_dump(),
            "content_sha256": "a" * 64,
        }
    )
    assert changed.id == file.id
    with pytest.raises(ValidationError):
        file.name = "new"


@pytest.mark.parametrize(
    "kind", [EntityType.CLASS, EntityType.METHOD, EntityType.SQL_CANDIDATE]
)
def test_basic_entity_types_roundtrip(kind: EntityType) -> None:
    entity = CodeEntity(
        repository_id="repo:one",
        logical_key="A",
        entity_type=kind,
        id=logical_id("repo:one", kind, "A"),
        name="A",
        source_range=SourceRange(
            source_file_id=source_file().id,
            start=Position(line=1, byte_column=0),
            end=Position(line=2, byte_column=0),
        ),
    )
    assert EntityDocument.model_validate_json(entity.model_dump_json()).root == entity


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "../A", "a/../A", "a//A", "./A", "A/", "C:/A", "a\\A", "a\0A"],
)
def test_noncanonical_paths_are_rejected(path: str) -> None:
    with pytest.raises(ValidationError):
        source_file(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "ucm:" + "0" * 64},
        {"contract_version": 2},
        {"surprise": "value"},
        {"name": " "},
        {"content_sha256": "not-a-hash"},
        {"logical_key": "different"},
    ],
)
def test_invalid_envelopes_are_rejected(changes: dict) -> None:
    with pytest.raises(ValidationError):
        SourceFile.model_validate({**source_file().model_dump(), **changes})


@pytest.mark.parametrize("line,column", [(0, 0), (1, -1), (True, 0), ("1", 0)])
def test_invalid_positions_are_rejected(line: object, column: object) -> None:
    with pytest.raises(ValidationError):
        Position(line=line, byte_column=column)


def test_ranges_are_half_open_ordered_and_allow_empty() -> None:
    position = Position(line=2, byte_column=4)
    assert SourceRange(source_file_id=source_file().id, start=position, end=position)
    with pytest.raises(ValidationError):
        SourceRange(
            source_file_id=source_file().id,
            start=position,
            end=Position(line=2, byte_column=3),
        )


def test_exported_schema_is_current_and_covers_registry() -> None:
    schema = entity_json_schema()
    assert schema == json.loads(
        (Path(__file__).parents[1] / "docs/ucm-entity.schema.json").read_text()
    )
    assert set(schema["discriminator"]["mapping"]) == {
        kind.value for kind in EntityType
    }
    assert schema["$defs"]["SourceFile"]["additionalProperties"] is False
