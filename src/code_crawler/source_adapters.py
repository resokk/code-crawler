"""Explicit source adapter contracts, immutable routing and captured-byte orchestration."""

import asyncio
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

import asyncpg
from pydantic import Field, model_validator

from code_crawler.incremental import (
    FileAnalysis,
    IncrementalResult,
    SourceInput,
    _capture,
    _path,
    index_incremental,
)
from code_crawler.source_routing import source_language, valid_suffix
from code_crawler.ucm import (
    ContractModel,
    Coverage,
    EntityType,
    ExternalReference,
    Relation,
    SourceAnalysis,
    SourceDiagnostic,
    SourceFile,
    SourceRange,
    Text,
    logical_id,
)

_RANK = {"UNSUPPORTED": 0, "PARTIAL": 1, "COMPLETE": 2}


class SourceRoute(ContractModel):
    suffix: Text
    language: Text

    @model_validator(mode="after")
    def valid_route(self) -> "SourceRoute":
        if not valid_suffix(self.suffix) or self.language == "unknown":
            raise ValueError("invalid source suffix/language route")
        return self


class AdapterDescriptor(ContractModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    version: Text
    routes: tuple[SourceRoute, ...] = Field(min_length=1)
    capabilities: tuple[Coverage, ...] = Field(min_length=1)
    entity_types: tuple[EntityType, ...]

    @model_validator(mode="after")
    def unique_metadata(self) -> "AdapterDescriptor":
        if len({r.suffix for r in self.routes}) != len(self.routes):
            raise ValueError("duplicate adapter suffix route")
        if len({c.capability for c in self.capabilities}) != len(self.capabilities):
            raise ValueError("duplicate adapter capability")
        if len(set(self.entity_types)) != len(self.entity_types) or any(
            t in (EntityType.SOURCE_FILE, EntityType.SOURCE_ANALYSIS)
            for t in self.entity_types
        ):
            raise ValueError("duplicate or orchestrator-owned entity type")
        return self

    def manifest(self) -> dict:
        """Return canonical descriptor metadata independent of registration order."""
        result = self.model_dump(mode="json")
        result["routes"].sort(key=lambda route: route["suffix"])
        result["capabilities"].sort(key=lambda capability: capability["capability"])
        result["entity_types"].sort()
        return result


class AdapterFileResult(ContractModel):
    analysis: FileAnalysis
    diagnostics: tuple[SourceDiagnostic, ...] = ()
    capabilities: tuple[Coverage, ...] = ()


class PreparedAdapter(Protocol):
    analysis_version: str

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        """Analyze exactly the requested routed files; never read ambient source bytes."""
        ...


class SourceAdapter(Protocol):
    descriptor: AdapterDescriptor

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        """Build one catalog/profile from the adapter's routed captured sources."""
        ...


@dataclass(frozen=True)
class AdapterIssue:
    path: str | None
    diagnostic: SourceDiagnostic


class AdapterError(ValueError):
    def __init__(
        self, adapter_key: str, stage: str, issues: tuple[AdapterIssue, ...]
    ) -> None:
        self.adapter_key = adapter_key
        self.stage = stage
        self.issues = issues
        details = "; ".join(
            (issue.path + ": " if issue.path else "") + issue.diagnostic.message
            for issue in issues
        )
        super().__init__(adapter_key + " " + stage + ": " + details)


def _error(key: str, stage: str, error: Exception) -> AdapterError:
    return AdapterError(
        key,
        stage,
        (
            AdapterIssue(
                None,
                SourceDiagnostic(
                    severity="ERROR",
                    code="ADAPTER_" + stage.upper() + "_FAILED",
                    message=str(error).strip() or type(error).__name__,
                ),
            ),
        ),
    )


def _range(source: SourceInput, location: SourceRange | None) -> None:
    if location is None:
        return
    if location.source_file_id != source.file.id:
        raise ValueError("diagnostic points outside its captured source file")
    lines = source.content.split(b"\n")
    if any(
        position.line > len(lines)
        or position.byte_column > len(lines[position.line - 1])
        for position in (location.start, location.end)
    ):
        raise ValueError("diagnostic range exceeds captured source bytes")


def _ranges(value: object):
    if isinstance(value, SourceRange):
        yield value
    elif isinstance(value, ContractModel):
        for field in type(value).model_fields:
            yield from _ranges(getattr(value, field))
    elif isinstance(value, (tuple, list)):
        for child in value:
            yield from _ranges(child)


def _sources(sources: tuple[SourceInput, ...]) -> dict[str, SourceInput]:
    result = {}
    repositories = set()
    for source in sources:
        if not isinstance(source, SourceInput) or not isinstance(source.content, bytes):
            raise TypeError("adapters require immutable captured SourceInput bytes")
        if not isinstance(source.file, SourceFile):
            raise TypeError("captured source requires a SourceFile envelope")
        SourceFile.model_validate_json(source.file.model_dump_json())
        path = source.file.path
        _path(path)
        if path in result:
            raise ValueError("duplicate captured source path")
        if hashlib.sha256(source.content).hexdigest() != source.file.content_sha256:
            raise ValueError("captured source hash mismatch")
        repositories.add(source.file.repository_id)
        result[path] = source
    if len(repositories) > 1:
        raise ValueError("adapter catalog must belong to one repository")
    return result


class AdapterRegistry:
    """An explicit set of adapters; exact suffix ownership cannot depend on ordering."""

    def __init__(self, adapters: tuple[SourceAdapter, ...]) -> None:
        self._adapters = {}
        self._descriptors = {}
        self._routes = {}
        for adapter in adapters:
            descriptor = AdapterDescriptor.model_validate_json(
                adapter.descriptor.model_dump_json()
            )
            if descriptor.key in self._adapters:
                raise ValueError("duplicate source adapter key")
            self._adapters[descriptor.key] = adapter
            self._descriptors[descriptor.key] = descriptor
            for route in descriptor.routes:
                if route.suffix in self._routes:
                    raise ValueError(
                        "ambiguous source suffix ownership: " + route.suffix
                    )
                self._routes[route.suffix] = (descriptor.key, route.language)

    @property
    def languages(self) -> dict[str, str]:
        return {suffix: route[1] for suffix, route in sorted(self._routes.items())}

    def describe(self) -> tuple[AdapterDescriptor, ...]:
        """Describe active adapters without touching the filesystem or database."""
        return tuple(self._descriptors[key] for key in sorted(self._descriptors))

    def route(self, path: str) -> AdapterDescriptor | None:
        """Choose one adapter using longest case-sensitive suffix match."""
        _path(path)
        suffixes = [suffix for suffix in self._routes if path.endswith(suffix)]
        return (
            self._descriptors[self._routes[max(suffixes, key=len)][0]]
            if suffixes
            else None
        )

    async def prepare(
        self, sources: tuple[SourceInput, ...]
    ) -> "PreparedSourceRegistry":
        """Prepare independent adapter catalogs against a validated captured inventory."""
        captured = await asyncio.to_thread(_sources, sources)
        prepared = {}
        for key, adapter in sorted(self._adapters.items()):
            descriptor = self._descriptors[key]
            if adapter.descriptor != descriptor:
                raise ValueError("adapter descriptor changed after registration")
            assigned = tuple(
                captured[path]
                for path in sorted(captured)
                if (route := self.route(path)) is not None and route.key == key
            )
            if any(
                source.file.language
                != source_language(source.file.path, self.languages)
                for source in assigned
            ):
                raise ValueError("captured language does not match registry route")
            try:
                implementation = await adapter.prepare(assigned)
                if (
                    not isinstance(implementation.analysis_version, str)
                    or not implementation.analysis_version.strip()
                ):
                    raise ValueError(
                        "prepared adapter must expose a nonblank analysis_version"
                    )
            except AdapterError:
                raise
            except Exception as error:
                raise _error(key, "prepare", error) from error
            prepared[key] = (
                descriptor,
                implementation,
                implementation.analysis_version,
            )
        return PreparedSourceRegistry(self, captured, prepared)


class PreparedSourceRegistry:
    """Incremental callback retaining the exact prepared source/catalog identity."""

    def __init__(
        self,
        registry: AdapterRegistry,
        captured: dict[str, SourceInput],
        prepared: dict[str, tuple[AdapterDescriptor, PreparedAdapter, str]],
    ) -> None:
        self.registry = registry
        self.captured = MappingProxyType(dict(captured))
        self.prepared = MappingProxyType(dict(prepared))
        payload = [
            [descriptor.manifest(), version]
            for descriptor, _, version in prepared.values()
        ]
        self.analysis_version = (
            "source.registry/1:"
            + hashlib.sha256(
                json.dumps(
                    payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest()
        )

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[FileAnalysis, ...]:
        requested = await asyncio.to_thread(_sources, sources)
        groups = {key: [] for key in self.prepared}
        for path, source in requested.items():
            if self.captured.get(path) != source:
                raise ValueError(
                    "source differs from prepared adapter catalog; rebuild registry"
                )
            route = self.registry.route(path)
            if route is None:
                raise ValueError("unregistered source requested for analysis")
            groups[route.key].append(source)
        output = {}
        for key, assigned in sorted(groups.items()):
            if not assigned:
                continue
            descriptor, implementation, version = self.prepared[key]
            try:
                if self.registry._adapters[key].descriptor != descriptor:
                    raise ValueError("adapter descriptor changed after preparation")
                if implementation.analysis_version != version:
                    raise ValueError("prepared adapter version changed during analysis")
                results = await implementation(
                    tuple(sorted(assigned, key=lambda source: source.file.path))
                )
                if self.registry._adapters[key].descriptor != descriptor:
                    raise ValueError("adapter descriptor changed during analysis")
                if implementation.analysis_version != version:
                    raise ValueError("prepared adapter version changed during analysis")
                converted = await asyncio.to_thread(
                    self._validate,
                    descriptor,
                    version,
                    tuple(assigned),
                    results,
                    self.captured,
                )
            except AdapterError:
                raise
            except Exception as error:
                raise _error(key, "analyze", error) from error
            output.update({result.path: result for result in converted})
        return tuple(output[path] for path in sorted(output))

    @staticmethod
    def _validate(
        descriptor: AdapterDescriptor,
        version: str,
        sources: tuple[SourceInput, ...],
        results: tuple[AdapterFileResult, ...],
        captured: Mapping[str, SourceInput],
    ) -> tuple[FileAnalysis, ...]:
        if not isinstance(results, tuple) or any(
            not isinstance(result, AdapterFileResult) for result in results
        ):
            raise ValueError("adapter must return tuple[AdapterFileResult]")
        results = tuple(
            AdapterFileResult.model_validate_json(result.model_dump_json())
            for result in results
        )
        source_by_path = {source.file.path: source for source in sources}
        paths = [result.analysis.path for result in results]
        if len(set(paths)) != len(paths) or set(paths) != set(source_by_path):
            raise ValueError("adapter must return each requested file exactly once")
        declared = {
            capability.capability: capability for capability in descriptor.capabilities
        }
        output = []
        by_id = {source.file.id: source for source in captured.values()}
        for result in results:
            source = source_by_path[result.analysis.path]
            for diagnostic in result.diagnostics:
                _range(source, diagnostic.source_range)
            capabilities = result.capabilities or descriptor.capabilities
            reported = {c.capability: c for c in capabilities}
            if len(reported) != len(capabilities) or set(reported) != set(declared):
                raise ValueError(
                    "per-file capabilities must match the declared capability set"
                )
            for capability in capabilities:
                limit = declared[capability.capability]
                if (
                    capability.analyzer_version != limit.analyzer_version
                    or _RANK[capability.status] > _RANK[limit.status]
                ):
                    raise ValueError(
                        "per-file capability exceeds declared version/coverage"
                    )
            if result.analysis.entities and all(
                c.status == "UNSUPPORTED" for c in capabilities
            ):
                raise ValueError(
                    "unsupported file analysis cannot assert semantic entities"
                )
            if any(d.severity == "ERROR" for d in result.diagnostics):
                capabilities = tuple(
                    Coverage(
                        capability=c.capability,
                        analyzer_version=c.analyzer_version,
                        status="PARTIAL",
                        reasons=("error diagnostics present",),
                    )
                    if c.status == "COMPLETE"
                    else c
                    for c in capabilities
                )
            reported = {c.capability: c for c in capabilities}
            for entity in result.analysis.entities:
                for location in _ranges(entity):
                    referenced = by_id.get(location.source_file_id)
                    if referenced is None:
                        raise ValueError(
                            "fact source range points outside captured inventory"
                        )
                    _range(referenced, location)
                if entity.entity_type not in descriptor.entity_types:
                    raise ValueError(
                        "adapter emitted an undeclared/orchestrator-owned entity type"
                    )
                if entity.repository_id != source.file.repository_id:
                    raise ValueError("adapter emitted facts for another repository")
                if isinstance(entity, (Relation, ExternalReference)):
                    capability = reported.get(entity.coverage.capability)
                    if (
                        capability is None
                        or entity.coverage.analyzer_version
                        != capability.analyzer_version
                        or _RANK[entity.coverage.status] > _RANK[capability.status]
                    ):
                        raise ValueError(
                            "fact coverage is outside the adapter capability declaration"
                        )
            logical_key = json.dumps(
                ["source.analysis", source.file.id, descriptor.key],
                separators=(",", ":"),
            )
            report = SourceAnalysis(
                repository_id=source.file.repository_id,
                logical_key=logical_key,
                id=logical_id(
                    source.file.repository_id, EntityType.SOURCE_ANALYSIS, logical_key
                ),
                name=descriptor.key,
                source_file_id=source.file.id,
                adapter_key=descriptor.key,
                adapter_version=descriptor.version,
                analysis_version=version,
                capabilities=tuple(sorted(capabilities, key=lambda c: c.capability)),
                diagnostics=result.diagnostics,
            )
            output.append(
                FileAnalysis(
                    path=result.analysis.path,
                    entities=(*result.analysis.entities, report),
                    dependencies=result.analysis.dependencies,
                )
            )
        return tuple(output)


async def index_sources(
    conn: asyncpg.Connection, repository_id: UUID, root: Path, registry: AdapterRegistry
) -> IncrementalResult:
    """Route captured sources through independent adapters into one BUILDING snapshot."""
    root = await asyncio.to_thread(root.resolve, strict=True)
    captured = await _capture(root, repository_id, registry.languages)
    prepared = await registry.prepare(captured.sources)
    return await index_incremental(
        conn,
        repository_id,
        root,
        prepared,
        languages=registry.languages,
        analysis_version=prepared.analysis_version,
    )
