"""Captured PL/Plus producer for the canonical source adapter registry."""

import asyncio
from dataclasses import dataclass

from code_crawler.incremental import SourceInput, tick
from code_crawler.plplus_ucm import analyze_plplus, capabilities, catalog_plplus
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
        version, catalog = await asyncio.to_thread(catalog_plplus, sources)
        return _PreparedPlplus(version, catalog)


@dataclass(frozen=True)
class _PreparedPlplus:
    analysis_version: str
    catalog: tuple

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        captured = {entry.source.file.path: entry.source for entry in self.catalog}

        def analyze() -> tuple[AdapterFileResult, ...]:
            results = []
            for source in sources:
                # KeyError, как и раньше: файл вне каталога анализировать нельзя.
                results.append(analyze_plplus(captured[source.file.path], self.catalog))
                tick("PL/Plus: анализ", len(sources))
            return tuple(results)

        return await asyncio.to_thread(analyze)
