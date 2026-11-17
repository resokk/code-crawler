"""Dedicated Kafka producer augmenting the canonical Java adapter and its catalogs."""

import asyncio
import hashlib
import json
import posixpath
from dataclasses import dataclass, field

import yaml

from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.java_adapter import JavaSourceAdapter, _PreparedJava
from code_crawler.kafka_java import CAPABILITY, CONFIG_KEYS, VERSION, Collector
from code_crawler.openapi_adapter import _parse
from code_crawler.source_adapters import (
    AdapterCatalog,
    AdapterDescriptor,
    AdapterFileResult,
    PreparedAdapter,
    SourceRoute,
)
from code_crawler.ucm import (
    Certainty,
    EntityRef,
    EntityType,
    Evidence,
    Position,
    Relation,
    RelationKind,
    Resolution,
    SourceDiagnostic,
    SourceRange,
    Symbol,
    Value,
    logical_id,
)


@dataclass(frozen=True)
class KafkaSourceAdapter:
    java_adapter: JavaSourceAdapter = field(default_factory=JavaSourceAdapter)

    @property
    def descriptor(self) -> AdapterDescriptor:
        base = self.java_adapter.descriptor
        return AdapterDescriptor(
            key=base.key,
            version=VERSION + ":" + base.version,
            routes=(
                *base.routes,
                SourceRoute(suffix=".properties", language="properties"),
            ),
            capabilities=(*base.capabilities, CAPABILITY),
            entity_types=tuple(
                dict.fromkeys(
                    (
                        *base.entity_types,
                        EntityType.SYMBOL,
                        EntityType.VALUE,
                        EntityType.RELATION,
                        EntityType.EXTERNAL_REFERENCE,
                    )
                )
            ),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        return await self.prepare_inventory(sources, sources)

    async def prepare_inventory(
        self, assigned: tuple[SourceInput, ...], inventory: tuple[SourceInput, ...]
    ) -> PreparedAdapter:
        java_sources = tuple(s for s in assigned if s.file.path.endswith(".java"))
        base = await self.java_adapter.prepare(java_sources)
        pairs = await base.symbol_results()
        config_sources = tuple(s for s in inventory if _configuration_path(s.file.path))
        extras = await asyncio.to_thread(_analyze, pairs, config_sources, assigned)
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    (s.file.path, s.file.content_sha256)
                    for s in sorted(
                        (*java_sources, *config_sources), key=lambda s: s.file.path
                    )
                ],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return _Prepared(
            base,
            extras,
            self.descriptor,
            VERSION + ":" + base.analysis_version + ":" + fingerprint,
        )


def _configuration_path(path: str) -> bool:
    name = posixpath.basename(path)
    return (
        name == "application.properties"
        or name in ("application.yml", "application.yaml")
        or (
            name.startswith("application-")
            and name.endswith((".properties", ".yml", ".yaml"))
        )
    )


def _location(source: SourceInput) -> SourceRange:
    lines = source.content.split(b"\n")
    return SourceRange(
        source_file_id=source.file.id,
        start=Position(line=1, byte_column=0),
        end=Position(line=len(lines), byte_column=len(lines[-1])),
    )


def _config(source: SourceInput) -> tuple[dict[str, str], tuple[SourceDiagnostic, ...]]:
    values = {}
    diagnostics = []

    def issue(message):
        diagnostics.append(
            SourceDiagnostic(
                severity="WARNING", code="kafka.CONFIG_PARTIAL", message=message
            )
        )

    try:
        if len(source.content) > 1024 * 1024:
            raise ValueError("Kafka configuration exceeds 1 MiB")
        if source.file.path.endswith((".yaml", ".yml")):
            document = _parse(source)
            for parts, value in document.values.items():
                if isinstance(value, (str, int, bool)):
                    key = ".".join(parts)
                    values[key] = str(value)
        else:
            for line in source.content.decode("utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "!")):
                    continue
                if line.endswith("\\") or "=" not in line:
                    issue(
                        "Only literal key=value properties are supported; config context is unknown."
                    )
                    return {}, tuple(diagnostics)
                key, value = (part.strip() for part in line.split("=", 1))
                if key in values:
                    issue(
                        "Duplicate configuration key; effective context is not inferred."
                    )
                    return {}, tuple(diagnostics)
                values[key] = value
    except (
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
        yaml.YAMLError,
    ) as error:
        issue(str(error))
        return {}, tuple(diagnostics)
    output = {}
    for key, value in values.items():
        if any(c in value for c in ("${", "#{", "\0")):
            if key.startswith("spring.kafka.") or key == "spring.profiles.active":
                issue(
                    "Dynamic configuration value; cluster/serde/environment is not inferred."
                )
            continue
        if key == "spring.profiles.active":
            output["environment"] = value
        if not key.startswith("spring.kafka."):
            continue
        key = key.removeprefix("spring.kafka.")
        key = key.removeprefix("properties.")
        for group in ("producer.", "consumer."):
            if key.startswith(group):
                # Keep producer and consumer context distinct until selected per endpoint.
                suffix = (
                    key.removeprefix(group)
                    .removeprefix("properties.")
                    .replace("-", ".")
                )
                if suffix in CONFIG_KEYS:
                    output[group + suffix] = value
                break
        else:
            key = key.replace("-", ".")
            if key in CONFIG_KEYS:
                output[key] = value
    return output, tuple(diagnostics)


def _configuration_result(
    source: SourceInput,
    config: dict[str, str],
    diagnostics: tuple[SourceDiagnostic, ...],
) -> AdapterFileResult:
    entities = []
    if config:
        repo = source.file.repository_id
        key = json.dumps(["kafka.config", source.file.path], separators=(",", ":"))
        symbol = Symbol(
            repository_id=repo,
            id=logical_id(repo, EntityType.SYMBOL, key),
            logical_key=key,
            name=source.file.path,
            symbol_kind="KAFKA_CONFIGURATION",
            qualified_name="kafka.config::" + source.file.path,
            source_range=_location(source),
        )
        entities.append(symbol)
        for name, value in sorted(config.items()):
            logical_key = json.dumps([key, name], separators=(",", ":"))
            literal = Value(
                repository_id=repo,
                id=logical_id(repo, EntityType.VALUE, logical_key),
                logical_key=logical_key,
                name=name,
                value_kind="LITERAL",
                literal=value,
                source_range=_location(source),
            )
            entities.append(literal)
            rel_key = logical_key + ":attribute"
            entities.append(
                Relation(
                    repository_id=repo,
                    id=logical_id(repo, EntityType.RELATION, rel_key),
                    logical_key=rel_key,
                    name=name,
                    source_range=_location(source),
                    relation_kind=RelationKind.KAFKA_ATTRIBUTE,
                    source=EntityRef(id=symbol.id, entity_type=symbol.entity_type),
                    resolution=Resolution(
                        status="RESOLVED",
                        target=EntityRef(
                            id=literal.id, entity_type=literal.entity_type
                        ),
                    ),
                    certainty=Certainty.STATIC_PROVEN,
                    evidence=(
                        Evidence(
                            source_range=_location(source),
                            analyzer="kafka",
                            analyzer_version=VERSION,
                            rule="kafka.configuration",
                            description="Literal source configuration; effective deployment not asserted.",
                        ),
                    ),
                    coverage=CAPABILITY,
                )
            )
    return AdapterFileResult(
        analysis=FileAnalysis(path=source.file.path, entities=tuple(entities)),
        diagnostics=diagnostics,
    )


def _analyze(pairs, configs, assigned):
    collector = Collector(pairs)
    parsed = {source.file.path: _config(source) for source in configs}
    sources = {source.file.path: source for source in configs}
    results = {}
    for source, _ in pairs:
        path = source.file.path
        directory = posixpath.dirname(path)
        # Common Spring resources and root layouts are explicit candidates, not runtime wiring.
        candidates = []
        while True:
            for suffix in (
                "application.properties",
                "application.yaml",
                "application.yml",
                "src/main/resources/application.properties",
                "src/main/resources/application.yaml",
                "src/main/resources/application.yml",
            ):
                candidates.append(posixpath.join(directory, suffix))
            if not directory:
                break
            directory = posixpath.dirname(directory)
        present = [p for p in dict.fromkeys(candidates) if p in parsed]
        config, evidence = {}, ()
        if len(present) == 1:
            config = parsed[present[0]][0]
            evidence = (
                Evidence(
                    source_range=_location(sources[present[0]]),
                    analyzer="kafka",
                    analyzer_version=VERSION,
                    rule="kafka.configuration-candidate",
                    description="Captured application config candidate; Spring factory/override selection is not proved.",
                ),
            )
        results[path] = collector.analyze(
            path, config, evidence, tuple(sorted(set(candidates)))
        )
        config_warnings = tuple(d for p in present for d in parsed[p][1])
        if config_warnings:
            results[path] = results[path].model_copy(
                update={"diagnostics": (*results[path].diagnostics, *config_warnings)}
            )
        if len(present) > 1:
            warning = SourceDiagnostic(
                severity="WARNING",
                code="kafka.AMBIGUOUS_CONFIGURATION",
                message="Multiple application configurations are candidates; no cluster/environment is selected.",
            )
            results[path] = results[path].model_copy(
                update={"diagnostics": (*results[path].diagnostics, warning)}
            )
    for source in assigned:
        if source.file.path.endswith(".properties"):
            config, diagnostics = parsed.get(source.file.path, ({}, ()))
            results[source.file.path] = _configuration_result(
                source, config, diagnostics
            )
    return results


@dataclass(frozen=True)
class _Prepared:
    java: _PreparedJava
    extras: dict[str, AdapterFileResult]
    descriptor: AdapterDescriptor
    analysis_version: str

    async def aclose(self, *, abort: bool = False) -> None:
        await self.java.aclose(abort=abort)

    async def export_catalogs(self) -> tuple[AdapterCatalog, ...]:
        return await self.java.export_catalogs()

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        java_results = await self.java(
            tuple(s for s in sources if s.file.path.endswith(".java"))
        )
        return await asyncio.to_thread(self.combine, sources, java_results)

    def combine(
        self,
        sources: tuple[SourceInput, ...],
        java_results: tuple[AdapterFileResult, ...],
    ) -> tuple[AdapterFileResult, ...]:
        original = {result.analysis.path: result for result in java_results}
        results = []
        for source in sources:
            path = source.file.path
            extra = self.extras[path]
            base = original.get(path)
            capabilities = (
                base.capabilities or self.descriptor.capabilities[:-1]
                if base
                else tuple(
                    c.model_copy(
                        update={
                            "status": "UNSUPPORTED",
                            "reasons": ("Not a Java source file.",),
                        }
                    )
                    for c in self.descriptor.capabilities[:-1]
                )
            )
            analysis = FileAnalysis(
                path=path,
                entities=(
                    *(base.analysis.entities if base else ()),
                    *extra.analysis.entities,
                ),
                dependencies=tuple(
                    sorted(
                        {
                            *(base.analysis.dependencies if base else ()),
                            *extra.analysis.dependencies,
                        }
                    )
                ),
            )
            results.append(
                AdapterFileResult(
                    analysis=analysis,
                    diagnostics=(
                        *(base.diagnostics if base else ()),
                        *extra.diagnostics,
                    ),
                    capabilities=(*capabilities, CAPABILITY),
                )
            )
        return tuple(results)
