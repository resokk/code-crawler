"""Captured PL/Plus producer for the canonical source adapter registry."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from code_crawler.incremental import SourceInput
from code_crawler.plplus_ucm import build_plplus, capabilities
from code_crawler.source_adapters import (
    AdapterDescriptor,
    AdapterFileResult,
    PreparedAdapter,
    SourceRoute,
)
from code_crawler.ucm import EntityType


@dataclass(frozen=True)
class PlplusSourceAdapter:
    @property
    def descriptor(self) -> AdapterDescriptor:
        return AdapterDescriptor(
            key="plplus",
            version="1",
            routes=(SourceRoute(suffix=".plp", language="plplus"),),
            capabilities=capabilities(),
            entity_types=(
                EntityType.SYMBOL,
                EntityType.SCOPE,
                EntityType.OCCURRENCE,
                EntityType.RELATION,
                EntityType.EXTERNAL_REFERENCE,
            ),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        version, results = await asyncio.to_thread(build_plplus, sources)
        return _PreparedPlplus(version, MappingProxyType(results))


@dataclass(frozen=True)
class _PreparedPlplus:
    analysis_version: str
    results: Mapping[str, AdapterFileResult]

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        return tuple(self.results[source.file.path] for source in sources)
