"""Groovy producer for the captured-source adapter registry."""

import asyncio
from dataclasses import dataclass
from typing import Literal

from code_crawler.groovy_ucm import capabilities, extract_groovy
from code_crawler.incremental import SourceInput, tick
from code_crawler.source_adapters import (
    AdapterDescriptor,
    AdapterFileResult,
    PreparedAdapter,
    SourceRoute,
)
from code_crawler.ucm import EntityType


@dataclass(frozen=True)
class GroovySourceAdapter:
    dialect: Literal["postgres", "mysql", "tsql"] = "postgres"

    def __post_init__(self) -> None:
        if self.dialect not in ("postgres", "mysql", "tsql"):
            raise ValueError("invalid Groovy SQL dialect")

    @property
    def descriptor(self) -> AdapterDescriptor:
        return AdapterDescriptor(
            key="groovy",
            version="1",
            routes=tuple(
                SourceRoute(suffix=s, language="groovy")
                for s in (".groovy", ".gvy", ".gy", ".gsh", ".gradle")
            ),
            capabilities=capabilities(),
            entity_types=(
                EntityType.SYMBOL,
                EntityType.SCOPE,
                EntityType.OCCURRENCE,
                EntityType.EXTERNAL_REFERENCE,
                EntityType.RELATION,
                EntityType.SQL_CANDIDATE,
                EntityType.SQL_CONSTRUCTION,
                EntityType.SQL_STATEMENT,
                EntityType.DATA_ACCESS,
            ),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        return _PreparedGroovy(self.dialect)


@dataclass(frozen=True)
class _PreparedGroovy:
    dialect: str

    @property
    def analysis_version(self) -> str:
        return "groovy/1:antlr/4.13.2:sql/" + self.dialect

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        def analyze() -> tuple[AdapterFileResult, ...]:
            results = []
            for source in sources:
                results.append(extract_groovy(source, self.dialect))
                tick("Groovy: анализ", len(sources))
            return tuple(results)

        return await asyncio.to_thread(analyze)
