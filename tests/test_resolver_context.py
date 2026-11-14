from uuid import UUID

import pytest
from pydantic import ValidationError

from code_crawler.resolver_context import ResolverContext, Selection


def selection(n):
    return Selection(
        repository_key=f"repo{n}",
        repository_id=UUID(int=n),
        snapshot_id=UUID(int=n + 10),
        generation=UUID(int=n + 20),
        commit_hash="commit",
    )


def test_manifest_fingerprint_is_order_independent_and_version_sensitive():
    one, two = selection(1), selection(2)
    first = ResolverContext(mode="LATEST_INDEXED", selections=(one, two))
    assert (
        first.fingerprint
        == ResolverContext(mode="LATEST_INDEXED", selections=(two, one)).fingerprint
    )
    assert (
        first.fingerprint
        != ResolverContext(mode="PINNED_SNAPSHOTS", selections=(one, two)).fingerprint
    )
    assert (
        first.fingerprint
        != ResolverContext(
            mode="LATEST_INDEXED",
            selections=(one.model_copy(update={"generation": UUID(int=99)}), two),
        ).fingerprint
    )
    assert ResolverContext.model_validate_json(first.model_dump_json()) == first


def test_manifest_rejects_conflicting_versions_and_implicit_service_bindings():
    one = selection(1)
    for fields in (
        {"mode": "LATEST_INDEXED", "selections": (one, one)},
        {"mode": "DEPLOYMENT_CONTEXT", "selections": (one,)},
        {
            "mode": "LATEST_INDEXED",
            "selections": (one.model_copy(update={"services": ("prod",)}),),
        },
    ):
        with pytest.raises(ValidationError):
            ResolverContext(**fields)
