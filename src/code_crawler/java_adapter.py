"""Canonical Java analyzers exposed through the common source-adapter contract."""

import asyncio
from dataclasses import dataclass
from typing import Literal

from code_crawler import java
from code_crawler.database_resolution import ConnectionAssignment
from code_crawler.database_schema import SchemaImport
from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.java_calls import JavaCallAnalyzer
from code_crawler.java_database import JavaDatabaseAnalyzer
from code_crawler.java_execution import JavaExecutionAnalyzer
from code_crawler.java_lineage import JavaLineageAnalyzer
from code_crawler.java_orm import JavaOrmAnalyzer
from code_crawler.java_semantic import JavaSemanticAnalyzer
from code_crawler.java_sql import JavaSqlAnalyzer
from code_crawler.java_symbols import extract
from code_crawler.source_adapters import (
    AdapterDescriptor,
    AdapterError,
    AdapterFileResult,
    AdapterIssue,
    PreparedAdapter,
    SourceRoute,
)
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

    def __post_init__(self) -> None:
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
            version="1",
            routes=(SourceRoute(suffix=".java", language="java"),),
            capabilities=capabilities,
            entity_types=tuple(
                kind for group in _ENTITY_GROUPS[: index + 1] for kind in group
            ),
        )

    async def prepare(self, sources: tuple[SourceInput, ...]) -> PreparedAdapter:
        """Build the existing catalog without filesystem/database IO in the adapter."""
        if self.profile == "symbols":
            return _PreparedJava(self, None)

        def build() -> JavaCallAnalyzer:
            factories = {
                "calls": JavaCallAnalyzer,
                "sql": JavaSqlAnalyzer,
                "execution": JavaExecutionAnalyzer,
            }
            if self.profile in factories:
                return factories[self.profile](sources)
            if self.profile in ("semantic", "lineage"):
                return (
                    JavaSemanticAnalyzer
                    if self.profile == "semantic"
                    else JavaLineageAnalyzer
                )(sources, self.dialect)
            if self.profile == "database":
                return JavaDatabaseAnalyzer(
                    sources, self.schemas, self.assignments, self.dialect
                )
            return JavaOrmAnalyzer(
                sources,
                self.schemas,
                self.assignments,
                self.dialect,
                self.naming_policy,
            )

        try:
            analyzer = await asyncio.to_thread(build)
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
        return _PreparedJava(self, analyzer)


class _PreparedJava:
    def __init__(
        self, adapter: JavaSourceAdapter, analyzer: JavaCallAnalyzer | None
    ) -> None:
        self.adapter = adapter
        self.analyzer = analyzer
        self.analysis_version = (
            analyzer.analysis_version if analyzer else "java.symbols/1"
        )

    async def __call__(
        self, sources: tuple[SourceInput, ...]
    ) -> tuple[AdapterFileResult, ...]:
        if self.analyzer is None:

            def collect() -> tuple[AdapterFileResult, ...]:
                results = []
                for source in sources:
                    result = extract(source)
                    results.append(
                        AdapterFileResult(
                            analysis=result.analysis,
                            diagnostics=_diagnostics(source, result.diagnostics),
                            capabilities=(
                                self.adapter.descriptor.capabilities[0],
                                result.coverage,
                            ),
                        )
                    )
                return tuple(results)

            return await asyncio.to_thread(collect)
        analyses = await self.analyzer(sources)

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
                results.append(
                    AdapterFileResult(
                        analysis=analysis,
                        diagnostics=(
                            *_diagnostics(file.source, file.result.diagnostics),
                            *_semantic_diagnostics(file.source, analysis),
                        ),
                        capabilities=tuple(capabilities),
                    )
                )
            return tuple(results)

        return await asyncio.to_thread(collect)


def java_adapter_catalog() -> tuple[AdapterDescriptor, ...]:
    """Describe alternative built-in Java profiles; activate exactly one per suffix."""
    return tuple(
        JavaSourceAdapter(profile=profile).descriptor for profile in JAVA_PROFILES
    )
