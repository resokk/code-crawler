import asyncio

import pytest
from test_resolver_context import selection

from code_crawler.external_candidates import (
    normalize_selector,
    resolve_external_reference,
)
from code_crawler.resolver_context import ResolverContext
from code_crawler.ucm import DatabaseSelector, HttpSelector, SymbolSelector


def test_typed_selector_keys_preserve_signature_service_and_namespace():
    unknown = normalize_selector(SymbolSelector(qualified_name="api.A.m"))
    zero = normalize_selector(
        SymbolSelector(qualified_name="api.A.m", parameter_type_names=())
    )
    assert unknown.kind == "SYMBOL" and not unknown.complete
    assert (
        zero.kind == "SYMBOL_SIGNATURE"
        and zero.complete
        and zero.key == ("api.A.m", ())
    )
    assert (
        normalize_selector(HttpSelector(method="GET", path="/x", service="one")).key
        != normalize_selector(HttpSelector(method="GET", path="/x", service="two")).key
    )
    assert not normalize_selector(
        HttpSelector(method="GET", path="/x/{dynamic}")
    ).complete
    assert not normalize_selector(
        DatabaseSelector(connection="billing", table="Users")
    ).complete
    assert (
        normalize_selector(SymbolSelector(qualified_name="bpmn.process::order")).kind
        == "BPMN_PROCESS"
    )
    assert (
        normalize_selector(SymbolSelector(qualified_name="kafka.topic::order")).kind
        == "KAFKA_TOPIC"
    )


def test_invalid_or_denied_request_never_reads_database():
    context = ResolverContext(mode="LATEST_INDEXED", selections=(selection(1),))

    async def run():
        with pytest.raises(PermissionError):
            await resolve_external_reference(
                None,
                "repo1",
                "ucm:" + "a" * 64,
                context,
                allowed_repositories=frozenset(),
            )
        for changes in (
            {"reference_id": "bad"},
            {"limit": True},
            {"limit": 201},
            {"source_repository_key": "outside"},
        ):
            args = {
                "source_repository_key": "repo1",
                "reference_id": "ucm:" + "a" * 64,
                "limit": 10,
                **changes,
            }
            with pytest.raises(ValueError):
                await resolve_external_reference(
                    None,
                    context=context,
                    allowed_repositories=frozenset(("repo1",)),
                    **args,
                )

    asyncio.run(run())


def test_unknown_frameworks_and_parameter_types_never_become_complete_symbol_proof():
    for selector in (
        SymbolSelector(qualified_name="bpmn.class::handler", parameter_type_names=()),
        SymbolSelector(qualified_name="bpmn.process::p", parameter_type_names=()),
        SymbolSelector(
            qualified_name="api.Client.m", parameter_type_names=("unknown",)
        ),
        SymbolSelector(qualified_name="api.${type}.m", parameter_type_names=()),
    ):
        lookup = normalize_selector(selector)
        assert not lookup.complete and lookup.reasons
