"""Canonical Java analyzers exposed through the common source-adapter contract."""

import asyncio
from dataclasses import dataclass
from typing import Literal

from code_crawler import java
from code_crawler.database_resolution import ConnectionAssignment
from code_crawler.database_schema import SchemaImport
from code_crawler.http_facts import HTTP_COVERAGE, emit_java_http
from code_crawler.incremental import FileAnalysis, SourceInput, tick
from code_crawler.java_calls import JavaCallAnalyzer
from code_crawler.java_database import JavaDatabaseAnalyzer
from code_crawler.java_execution import JavaExecutionAnalyzer
from code_crawler.java_http_catalog import java_http_catalog, mentions_http
from code_crawler.java_lineage import JavaLineageAnalyzer
from code_crawler.java_orm import JavaOrmAnalyzer
from code_crawler.java_parallel import JavaProcessPool, WorkerConfig, validate_workers
from code_crawler.java_semantic import JavaSemanticAnalyzer
from code_crawler.java_sql import JavaSqlAnalyzer
from code_crawler.java_symbols import JavaSymbolsResult, extract
from code_crawler.source_adapters import (
    AdapterCatalog,
    AdapterDescriptor,
    AdapterError,
    AdapterFileResult,
    AdapterIssue,
    SourceRoute,
)
from code_crawler.sql_paths import SqlPathOptions
from code_crawler.ucm import (
    Coverage,
    EntityType,
    SourceDiagnostic,
    SourceRange,
    SqlStatement,
)

JavaProfile = Literal[
    "symbols", "calls", "sql", "execution", "semantic", "lineage", "database", "orm"
]
JAVA_PROFILES = (
    "symbols",
    "calls",
    "sql",
    "execution",
    "semantic",
    "lineage",
    "database",
    "orm",
)
_CAPABILITIES = (
    "java.symbols",
    "java.calls",
    "java.sql.construction",
    "java.sql.execution",
    "sql.semantic.access",
    "sql.parameter.lineage",
    "database.schema.identity",
    "jpa.orm.semantic",
)
_ENTITY_GROUPS = (
    (EntityType.SYMBOL, EntityType.SCOPE, EntityType.OCCURRENCE, EntityType.RELATION),
    (EntityType.EXTERNAL_REFERENCE,),
    (EntityType.SQL_CANDIDATE, EntityType.SQL_CONSTRUCTION),
    (EntityType.OPERATION, EntityType.VALUE, EntityType.SQL_EXECUTE),
    (EntityType.SQL_STATEMENT, EntityType.DATA_ACCESS),
    (EntityType.SQL_BINDING, EntityType.SQL_PLACEHOLDER),
    (
        EntityType.DATABASE_CONTEXT,
        EntityType.DATABASE_OBJECT,
        EntityType.DATABASE_ACCESS,
    ),
    (EntityType.ORM_MAPPING, EntityType.ORM_QUERY, EntityType.ORM_OPERATION),
)


def _diagnostics(
    source: SourceInput, diagnostics: tuple[java.Diagnostic, ...]
) -> tuple[SourceDiagnostic, ...]:
    return tuple(
        SourceDiagnostic(
            severity=d.severity,
            code="java." + d.code,
            message=d.message,
            source_range=SourceRange(
                source_file_id=source.file.id,
                start=d.source_span.start,
                end=d.source_span.end,
            ),
        )
        for d in diagnostics
    )


def _semantic_diagnostics(
    source: SourceInput, analysis: FileAnalysis
) -> tuple[SourceDiagnostic, ...]:
    return tuple(
        SourceDiagnostic(
            severity="ERROR",
            code="sql.CANDIDATE_PARSE_ERROR",
            message="SQL candidate parse error: " + "; ".join(entity.reasons),
            source_range=entity.source_range
            if entity.source_range is not None
            and entity.source_range.source_file_id == source.file.id
            else None,
        )
        for entity in analysis.entities
        if isinstance(entity, SqlStatement) and entity.parse_status == "ERROR"
    )


@dataclass(frozen=True)
class JavaSourceAdapter:
    profile: JavaProfile = "orm"
    schemas: tuple[SchemaImport, ...] = ()
    assignments: tuple[ConnectionAssignment, ...] = ()
    dialect: Literal["postgres", "mysql", "tsql"] = "postgres"
    naming_policy: Literal["UNKNOWN", "IDENTITY"] = "UNKNOWN"
    sql_options: SqlPathOptions | None = None
    analysis_workers: int = 1

    def __post_init__(self) -> None:
        validate_workers(self.analysis_workers)
        if (
            self.profile in ("symbols", "calls")
            and self.sql_options is not None
            and (
                self.sql_options.max_paths != 256
                or self.sql_options.on_method is not None
            )
        ):
            raise ValueError("SQL path options require a SQL-enabled Java profile")
        if (
            self.profile not in JAVA_PROFILES
            or self.dialect not in ("postgres", "mysql", "tsql")
            or self.naming_policy not in ("UNKNOWN", "IDENTITY")
        ):
            raise ValueError("invalid Java source adapter profile/options")
        if self.profile not in ("database", "orm") and (
            self.schemas or self.assignments
        ):
            raise ValueError("schema/connection options require database/orm profile")
        if self.profile != "orm" and self.naming_policy != "UNKNOWN":
            raise ValueError("physical naming policy requires orm profile")
        if (
            self.profile in ("symbols", "calls", "sql", "execution")
            and self.dialect != "postgres"
        ):
            raise ValueError(
                "dialect option requires semantic/lineage/database/orm profile"
            )

    @property
    def descriptor(self) -> AdapterDescriptor:
        index = JAVA_PROFILES.index(self.profile)
        capabilities = (
            Coverage(
                capability="java.parser.diagnostics",
                analyzer_version="1",
                status="COMPLETE",
            ),
            *(
                Coverage(
                    capability=name,
                    analyzer_version="1",
                    status="PARTIAL",
                    reasons=(
                        "bounded static coverage; see the corresponding Java adapter contract",
                    ),
                )
                for name in _CAPABILITIES[: index + 1]
            ),
        )
        return AdapterDescriptor(
            key="java." + self.profile,
            version="2",
            routes=(SourceRoute(suffix=".java", language="java"),),
            capabilities=(*capabilities, HTTP_COVERAGE),
            entity_types=tuple(
                dict.fromkeys(
                    (
                        *[
                            kind
                            for group in _ENTITY_GROUPS[: index + 1]
                            for kind in group
                        ],
                        EntityType.VALUE,
                        EntityType.EXTERNAL_REFERENCE,
                    )
                )
            ),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> "_PreparedJava":
        """Build the existing catalog without filesystem/database IO in the adapter."""
        if self.profile == "symbols":
            prepared = _PreparedJava(self, None, sources)
            await prepared.prepare_http()
            return prepared

        try:
            analyzer = await asyncio.to_thread(_build_analyzer, self, sources)
        except ValueError as error:
            issues = []
            # Only failed catalog construction reparses to preserve structured parser errors.
            for source in sources:
                parsed = await asyncio.to_thread(java.analyze, source.content)
                issues.extend(
                    AdapterIssue(source.file.path, diagnostic)
                    for diagnostic in _diagnostics(source, parsed.diagnostics)
                )
            if issues:
                raise AdapterError(
                    self.descriptor.key, "prepare", tuple(issues)
                ) from error
            raise
        prepared = _PreparedJava(self, analyzer, sources)
        await prepared.prepare_http()
        return prepared


def _build_analyzer(
    adapter: JavaSourceAdapter, sources: tuple[SourceInput, ...]
) -> JavaCallAnalyzer:
    factories = {
        "calls": JavaCallAnalyzer,
        "sql": JavaSqlAnalyzer,
        "execution": JavaExecutionAnalyzer,
    }
    if adapter.profile in factories:
        return (
            factories[adapter.profile](sources)
            if adapter.profile == "calls"
            else factories[adapter.profile](sources, sql_options=adapter.sql_options)
        )
    if adapter.profile in ("semantic", "lineage"):
        return (
            JavaSemanticAnalyzer
            if adapter.profile == "semantic"
            else JavaLineageAnalyzer
        )(sources, adapter.dialect, sql_options=adapter.sql_options)
    if adapter.profile == "database":
        return JavaDatabaseAnalyzer(
            sources,
            adapter.schemas,
            adapter.assignments,
            adapter.dialect,
            sql_options=adapter.sql_options,
        )
    return JavaOrmAnalyzer(
        sources,
        adapter.schemas,
        adapter.assignments,
        adapter.dialect,
        adapter.naming_policy,
        sql_options=adapter.sql_options,
    )


class _PreparedJava:
    def __init__(
        self,
        adapter: JavaSourceAdapter,
        analyzer: JavaCallAnalyzer | None,
        sources: tuple[SourceInput, ...],
    ) -> None:
        self.adapter = adapter
        self.sources = sources
        self._symbol_catalog = {}
        self.analyzer = analyzer
        self._parallel: JavaProcessPool | None = None
        self._parallel_lock = asyncio.Lock()
        self.analysis_version = (
            analyzer.analysis_version if analyzer else "java.symbols/1"
        )

    def _pairs(self):
        if self.analyzer is None:
            for source in self.sources:
                if source.file.path not in self._symbol_catalog:
                    self._symbol_catalog[source.file.path] = extract(source)
            return tuple(
                (source, self._symbol_catalog[source.file.path])
                for source in self.sources
            )
        return tuple(
            (source, self.analyzer.files[source.file.path].result)
            for source in self.sources
        )

    async def prepare_http(self) -> None:
        def build():
            if mentions_http(self.sources):
                self._http_catalog = java_http_catalog(
                    self._pairs(), self.adapter.profile
                )
                self.analysis_version += ":" + self._http_catalog.version
            else:
                self._http_catalog = None

        await asyncio.to_thread(build)

    async def export_catalogs(self) -> tuple["AdapterCatalog", ...]:
        from code_crawler.bpmn_java_catalog import java_binding_catalog

        def collect():
            pairs = self._pairs()
            http = self._http_catalog or java_http_catalog(pairs, self.adapter.profile)
            self._http_catalog = http
            return (java_binding_catalog(pairs, self.adapter.profile), http)

        return await asyncio.to_thread(collect)

    async def symbol_results(self) -> tuple[tuple[SourceInput, JavaSymbolsResult], ...]:
        """Share already parsed canonical ASTs with optional local producers."""
        return await asyncio.to_thread(self._pairs)

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        if self.analyzer is None:

            def collect() -> tuple[AdapterFileResult, ...]:
                results = []
                for source in sources:
                    result = self._symbol_catalog.get(source.file.path) or extract(
                        source
                    )
                    analysis = result.analysis
                    diagnostics = ()
                    if self._http_catalog is not None:
                        analysis, diagnostics = emit_java_http(
                            source, analysis, self._http_catalog
                        )
                    results.append(
                        AdapterFileResult(
                            analysis=analysis,
                            diagnostics=(
                                *_diagnostics(source, result.diagnostics),
                                *diagnostics,
                            ),
                            capabilities=(
                                self.adapter.descriptor.capabilities[0],
                                result.coverage,
                                HTTP_COVERAGE,
                            ),
                        )
                    )
                    tick("Java: символы", len(sources))
                return tuple(results)

            return await asyncio.to_thread(collect)
        if self.adapter.analysis_workers == 1:
            analyses = await self.analyzer(sources)
        elif not sources:
            analyses = ()
        else:
            for source in sources:
                context = self.analyzer.files.get(source.file.path)
                if context is None or context.source != source:
                    raise ValueError(
                        "Java catalog does not match captured source; rebuild analyzer"
                    )
            async with self._parallel_lock:
                if self._parallel is None:
                    options = self.adapter.sql_options or SqlPathOptions()
                    config = WorkerConfig(
                        sources=self.sources,
                        profile=self.adapter.profile,
                        schemas=self.adapter.schemas,
                        assignments=self.adapter.assignments,
                        dialect=self.adapter.dialect,
                        naming_policy=self.adapter.naming_policy,
                        max_paths=options.max_paths,
                        report_enabled=options.on_method is not None,
                        expected_version=self.analyzer.analysis_version,
                    )
                    pending = asyncio.create_task(
                        asyncio.to_thread(
                            JavaProcessPool,
                            config,
                            min(self.adapter.analysis_workers, len(self.sources)),
                        )
                    )
                    try:
                        self._parallel = await asyncio.shield(pending)
                    except asyncio.CancelledError:
                        pool = await pending
                        await pool.aclose(abort=True)
                        raise
            analyses, events = await self._parallel.analyze(sources)
            callback = (
                self.adapter.sql_options.on_method if self.adapter.sql_options else None
            )
            if callback is not None:

                def replay():
                    for event in events:
                        callback(event)

                await asyncio.to_thread(replay)
            for _ in analyses:
                tick("Java: анализ", len(sources))

        def collect() -> tuple[AdapterFileResult, ...]:
            results = []
            for analysis in analyses:
                file = self.analyzer.files[analysis.path]
                capabilities = [
                    self.adapter.descriptor.capabilities[0],
                    file.result.coverage,
                ]
                for attribute in (
                    "coverage",
                    "sql_coverage",
                    "execution_coverage",
                    "semantic_coverage",
                    "lineage_coverage",
                    "database_coverage",
                    "orm_coverage",
                ):
                    coverage = getattr(self.analyzer, attribute, None)
                    if coverage is not None:
                        capabilities.append(coverage)
                diagnostics = ()
                if self._http_catalog is not None:
                    analysis, diagnostics = emit_java_http(
                        file.source, analysis, self._http_catalog
                    )
                capabilities.append(HTTP_COVERAGE)
                results.append(
                    AdapterFileResult(
                        analysis=analysis,
                        diagnostics=(
                            *_diagnostics(file.source, file.result.diagnostics),
                            *_semantic_diagnostics(file.source, analysis),
                            *diagnostics,
                        ),
                        capabilities=tuple(capabilities),
                    )
                )
            return tuple(results)

        return await asyncio.to_thread(collect)

    async def aclose(self, *, abort: bool = False) -> None:
        if self._parallel is not None:
            pool, self._parallel = self._parallel, None
            await pool.aclose(abort=abort)


def java_adapter_catalog() -> tuple[AdapterDescriptor, ...]:
    """Describe alternative built-in Java profiles; activate exactly one per suffix."""
    return tuple(
        JavaSourceAdapter(profile=profile).descriptor for profile in JAVA_PROFILES
    )
