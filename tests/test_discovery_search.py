import asyncio
import json

import pytest

from code_crawler import search


class NoDatabase:
    async def fetchval(self, *args):
        raise AssertionError("invalid input reached database")


@pytest.mark.parametrize(
    "options",
    [
        {"allowed_repository_keys": []},
        {"allowed_repository_keys": ["one"], "repository_keys": ["two"]},
        {"allowed_repository_keys": ["one"], "repository_keys": []},
        {"allowed_repository_keys": ["one"], "limit": 201},
        {"allowed_repository_keys": ["one"], "offset": 1},
        {"allowed_repository_keys": ["one"], "expected_fingerprint": "bad"},
        {"allowed_repository_keys": ["one"], "qualifier": {"sql": "injection"}},
        {"allowed_repository_keys": ["one"], "qualifier": {"parameter_types": [""]}},
        {"allowed_repository_keys": ["one"], "qualifier": {"parameter_types": None}},
        {"allowed_repository_keys": ["one"], "qualifier": {"parameter_types": ["\0"]}},
    ],
)
def test_invalid_or_denied_discovery_never_queries_database(options):
    with pytest.raises(ValueError):
        asyncio.run(
            search.search_discovery_entries(NoDatabase(), "SYMBOL", "app.A", **options)
        )


@pytest.mark.parametrize(
    "kind,qualifier",
    [
        ("DATABASE", {}),
        ("HTTP", {"method": "GET"}),
        ("KAFKA", {}),
        ("REFERENCE_DATA", {}),
        ("UNKNOWN", {}),
    ],
)
def test_qualified_resources_require_context(kind, qualifier):
    with pytest.raises(ValueError):
        asyncio.run(
            search.search_discovery_entries(
                NoDatabase(),
                kind,
                "name",
                allowed_repository_keys=["one"],
                qualifier=qualifier,
            )
        )


@pytest.mark.parametrize("key", ["", " ", "\0", "x" * 4097])
def test_invalid_lookup_key(key):
    with pytest.raises(ValueError):
        asyncio.run(
            search.search_discovery_entries(
                NoDatabase(), "SYMBOL", key, allowed_repository_keys=["one"]
            )
        )


def test_one_statement_unknown_repository_and_explicit_partial_results():
    class Connection:
        def __init__(self):
            self.calls = []

        async def fetchval(self, sql, *args):
            self.calls.append(args)
            return json.dumps(
                {
                    "generation_manifest": [
                        {
                            "repository_key": "missing",
                            "repository_id": None,
                            "snapshot_id": None,
                            "generation_id": None,
                        }
                    ],
                    "items": [],
                    "match_count_lower_bound": 0,
                }
            )

    conn = Connection()
    result = asyncio.run(
        search.search_discovery_entries(
            conn, "SYMBOL", "app.A", allowed_repository_keys=["missing"]
        )
    )
    assert len(conn.calls) == 1
    assert (
        result["availability"] == "PARTIAL"
        and result["coverage"]["status"] == "PARTIAL"
    )
    assert result["resolution"] == "UNRESOLVED"
    assert len(result["fingerprint"]) == 64
