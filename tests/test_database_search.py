import asyncio

import pytest

from code_crawler import search


@pytest.mark.parametrize(
    "options",
    [
        {"mode": "unknown"},
        {"table": None},
        {"database_key": "a"},
        {"schema_version_key": "v1"},
        {"database_object_id": "ucm:" + "a" * 64},
        {"mode": "RESOLVED_DATABASE_OBJECT"},
        {
            "mode": "RESOLVED_DATABASE_OBJECT",
            "database_key": "a",
            "schema_version_key": "v1",
            "table": None,
        },
        {"mode": "RESOLVED_DATABASE_OBJECT", "database_object_id": "db:" + "a" * 64},
        {"mode": "RESOLVED_DATABASE_OBJECT", "database_object_id": "not-id"},
        {"table": ""},
        {"column": ""},
        {"schema": "bad\0name"},
        {"limit": 0},
        {"limit": 201},
        {"limit": True},
        {"limit": 1.5},
        {
            "mode": "RESOLVED_DATABASE_OBJECT",
            "database_key": " ",
            "schema_version_key": "v1",
        },
    ],
)
def test_invalid_access_selector_fails_before_database_io(options):
    for query in (search.find_table_readers, search.find_table_writers):
        args = {"table": "users", **options}
        with pytest.raises(ValueError):
            asyncio.run(query(None, "repo", **args))
