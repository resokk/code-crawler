import pytest
from pydantic import ValidationError

from code_crawler.snapshots import RepositoryInput, SnapshotInput


@pytest.mark.parametrize(
    "fields",
    [
        {"repository_key": " "},
        {"display_name": ""},
        {"source": " "},
        {"extra": 1},
    ],
)
def test_repository_metadata_rejects_invalid_fields(fields: dict) -> None:
    with pytest.raises(ValidationError):
        RepositoryInput.model_validate(
            {
                "repository_key": "org/app",
                "display_name": "app",
                "source": "local",
                **fields,
            }
        )


@pytest.mark.parametrize(
    "fields",
    [
        {"commit_hash": " "},
        {"branch": " "},
        {"source_fingerprint": "bad"},
        {"source_fingerprint": "A" * 64},
        {"dirty": "false"},
    ],
)
def test_snapshot_metadata_rejects_invalid_fields(fields: dict) -> None:
    with pytest.raises(ValidationError):
        SnapshotInput.model_validate(
            {
                "commit_hash": "abc",
                "source_fingerprint": "a" * 64,
                "dirty": False,
                **fields,
            }
        )
