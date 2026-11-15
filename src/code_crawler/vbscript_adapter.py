"""Versioned, captured-byte VBScript producer; persistence belongs to orchestration."""

import asyncio
from dataclasses import dataclass
from itertools import product
from typing import Literal

from code_crawler.incremental import SourceInput, tick
from code_crawler.source_adapters import (
    AdapterDescriptor,
    AdapterFileResult,
    PreparedAdapter,
    SourceRoute,
)
from code_crawler.ucm import EntityType
from code_crawler.vbscript_ucm import capabilities, extract_vbscript


@dataclass(frozen=True)
class VbscriptSourceAdapter:
    dialect: Literal["postgres", "mysql", "tsql"] = "postgres"

    def __post_init__(self) -> None:
        if self.dialect not in ("postgres", "mysql", "tsql"):
            raise ValueError("invalid VBScript SQL dialect")

    @property
    def descriptor(self) -> AdapterDescriptor:
        return AdapterDescriptor(
            key="vbscript",
            version="1",
            routes=tuple(
                SourceRoute(suffix="." + "".join(chars), language="vbscript")
                for chars in product("vV", "bB", "sS")
            ),
            capabilities=capabilities(),
            entity_types=(
                EntityType.SYMBOL,
                EntityType.SCOPE,
                EntityType.OCCURRENCE,
                EntityType.OPERATION,
                EntityType.VALUE,
                EntityType.RELATION,
                EntityType.EXTERNAL_REFERENCE,
                EntityType.SQL_CANDIDATE,
                EntityType.SQL_CONSTRUCTION,
                EntityType.SQL_STATEMENT,
                EntityType.DATA_ACCESS,
                EntityType.SQL_EXECUTE,
            ),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        return _PreparedVbscript(self.dialect)


@dataclass(frozen=True)
class _PreparedVbscript:
    dialect: str

    @property
    def analysis_version(self) -> str:
        return f"vbscript/1:grammar/1:antlr/4.13.2:utf8:sql/{self.dialect}"

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        def analyze():
            results = []
            for source in sources:
                results.append(extract_vbscript(source, self.dialect))
                tick("VBScript: анализ", len(sources))
            return tuple(results)

        return await asyncio.to_thread(analyze)
