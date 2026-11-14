"""Opt-in Java execution plus statement-local SQL semantic accesses."""

import asyncio
from pathlib import Path
from uuid import UUID

import asyncpg
import sqlglot

from code_crawler.incremental import (
    FileAnalysis,
    IncrementalResult,
    SourceInput,
    _capture,
    index_incremental,
)
from code_crawler.java_calls import _File
from code_crawler.java_execution import JavaExecutionAnalyzer
from code_crawler.sql_semantic import DIALECTS, StatementAnalysis, analyze_statements
from code_crawler.ucm import (
    Certainty,
    Coverage,
    DataAccess,
    EntityRef,
    EntityType,
    Evidence,
    Relation,
    RelationKind,
    Resolution,
    SqlConstruction,
    SqlStatement,
    logical_id,
)

_EFFECT_RELATIONS = {
    "READ": RelationKind.READS_FROM,
    "INSERT": RelationKind.INSERTS_INTO,
    "UPDATE": RelationKind.UPDATES,
    "DELETE": RelationKind.DELETES_FROM,
    "MERGE": RelationKind.MERGES_INTO,
    "DDL": RelationKind.DDL_ON,
}


def _envelope(repository: str, kind: EntityType, key: str, name: str, location) -> dict:
    return {
        "repository_id": repository,
        "logical_key": key,
        "id": logical_id(repository, kind, key),
        "name": name,
        "source_range": location,
    }


def _relation(
    repository: str,
    key: str,
    kind: RelationKind,
    source: EntityRef,
    resolution: Resolution,
    evidence: Evidence,
    coverage: Coverage,
) -> Relation:
    return Relation(
        **_envelope(
            repository, EntityType.RELATION, key, kind.value, evidence.source_range
        ),
        relation_kind=kind,
        source=source,
        resolution=resolution,
        certainty=Certainty.INFERRED
        if resolution.status == "RESOLVED"
        else Certainty.UNKNOWN,
        evidence=(evidence,),
        coverage=coverage,
    )


class JavaSemanticAnalyzer(JavaExecutionAnalyzer):
    """Analyze each recovered candidate using an explicit SQL dialect profile."""

    def __init__(
        self, sources: tuple[SourceInput, ...], dialect: str = "postgres"
    ) -> None:
        if dialect not in DIALECTS:
            raise ValueError("unsupported SQL dialect profile")
        super().__init__(sources)
        self.dialect = dialect
        self.analysis_version = (
            f"java.sql.semantic/1:{dialect}:sqlglot/{sqlglot.__version__}:"
            + self.analysis_version
        )
        self.semantic_coverage = Coverage(
            capability="sql.semantic.access",
            analyzer_version="1",
            status="PARTIAL",
            reasons=(
                "database schema/connection identity and derived-output lineage are not available",
                "AST effects describe possible SQL behavior, not actual execution",
            ),
        )

    def analysis(self, file: _File) -> FileAnalysis:
        base = super().analysis(file)
        entities = list(base.entities)
        statements_by_construction: dict[str, list[SqlStatement]] = {}
        constructions = {
            e.id: e for e in base.entities if isinstance(e, SqlConstruction)
        }
        repository = file.source.file.repository_id
        for construction in constructions.values():
            location = construction.source_range
            statements_by_construction[construction.id] = []
            for variant in construction.variants:
                parsed = (
                    (
                        StatementAnalysis(
                            variant.text,
                            0,
                            len(variant.text),
                            "UNKNOWN",
                            "PARTIAL",
                            variant.partial_reasons,
                            (),
                        ),
                    )
                    if variant.partial
                    else analyze_statements(variant.text, self.dialect)
                )
                if not parsed:
                    parsed = (
                        StatementAnalysis(
                            variant.text,
                            0,
                            len(variant.text),
                            "UNKNOWN",
                            "UNSUPPORTED",
                            ("no SQL statement AST",),
                            (),
                        ),
                    )
                for index, result in enumerate(parsed):
                    key = variant.candidate_id + f":statement:{index}:{self.dialect}"
                    statement = SqlStatement(
                        **_envelope(
                            repository,
                            EntityType.SQL_STATEMENT,
                            key,
                            result.operation,
                            location,
                        ),
                        candidate_id=variant.candidate_id,
                        statement_index=index,
                        dialect=self.dialect,
                        text=result.text,
                        text_start=result.text_start,
                        text_end=result.text_end,
                        operation=result.operation,
                        parse_status=result.parse_status,
                        reasons=result.reasons,
                    )
                    entities.append(statement)
                    statements_by_construction[construction.id].append(statement)
                    evidence = Evidence(
                        source_range=location,
                        analyzer="sql.semantic",
                        analyzer_version="1",
                        rule="statement-ast",
                        description=f"Decoded candidate chars [{result.text_start},{result.text_end}); dialect={self.dialect}; Java origin range is not a decoded-character mapping",
                    )
                    entities.append(
                        _relation(
                            repository,
                            key + ":candidate",
                            RelationKind.HAS_SQL_STATEMENT,
                            EntityRef(
                                id=variant.candidate_id,
                                entity_type=EntityType.SQL_CANDIDATE,
                            ),
                            Resolution(
                                status="RESOLVED",
                                target=EntityRef(
                                    id=statement.id,
                                    entity_type=EntityType.SQL_STATEMENT,
                                ),
                            ),
                            evidence,
                            self.semantic_coverage,
                        )
                    )
                    for access_index, detail in enumerate(result.accesses):
                        access_key = key + f":access:{access_index}"
                        access = DataAccess(
                            **_envelope(
                                repository,
                                EntityType.DATA_ACCESS,
                                access_key,
                                detail.access_kind + " " + detail.object_kind,
                                location,
                            ),
                            statement_id=statement.id,
                            **detail.model_dump(),
                        )
                        entities.append(access)
                        entities.append(
                            _relation(
                                repository,
                                access_key + ":effect",
                                _EFFECT_RELATIONS[access.access_kind],
                                EntityRef(
                                    id=statement.id,
                                    entity_type=EntityType.SQL_STATEMENT,
                                ),
                                Resolution(
                                    status="RESOLVED",
                                    target=EntityRef(
                                        id=access.id, entity_type=EntityType.DATA_ACCESS
                                    ),
                                ),
                                evidence,
                                self.semantic_coverage,
                            )
                        )
        for usage in base.entities:
            if (
                not isinstance(usage, Relation)
                or usage.relation_kind != RelationKind.USES_SQL_CONSTRUCTION
            ):
                continue
            refs = (
                (usage.resolution.target,)
                if usage.resolution.target
                else usage.resolution.candidates
            )
            linked = [
                (constructions[ref.id], statement)
                for ref in refs
                for statement in statements_by_construction.get(ref.id, ())
            ]
            key = usage.logical_key + ":statements"
            evidence = usage.evidence[0]
            if not linked:
                entities.append(
                    _relation(
                        repository,
                        key,
                        RelationKind.EXECUTES_STATEMENT,
                        usage.source,
                        Resolution(
                            status="UNRESOLVED",
                            reason=usage.resolution.reason
                            or "no recovered SQL statement origin",
                        ),
                        evidence,
                        self.semantic_coverage,
                    )
                )
            for construction, statement in linked:
                definite = (
                    usage.resolution.status == "RESOLVED"
                    and len(construction.variants) == 1
                    and statement.parse_status == "COMPLETE"
                )
                target = EntityRef(
                    id=statement.id, entity_type=EntityType.SQL_STATEMENT
                )
                resolution = (
                    Resolution(status="RESOLVED", target=target)
                    if definite
                    else Resolution(
                        status="PARTIAL",
                        candidates=(target,),
                        reason=usage.resolution.reason
                        or "alternative SQL variants or incomplete statement semantics",
                    )
                )
                entities.append(
                    _relation(
                        repository,
                        key + ":" + statement.id,
                        RelationKind.EXECUTES_STATEMENT,
                        usage.source,
                        resolution,
                        evidence,
                        self.semantic_coverage,
                    )
                )
        return FileAnalysis(
            path=base.path, entities=tuple(entities), dependencies=base.dependencies
        )


async def index_java_semantic(
    conn: asyncpg.Connection, repository_id: UUID, root: Path, dialect: str = "postgres"
) -> IncrementalResult:
    """Build semantic facts in a BUILDING snapshot; publication remains explicit."""
    if dialect not in DIALECTS:
        raise ValueError("unsupported SQL dialect profile")
    root = await asyncio.to_thread(root.resolve, strict=True)
    captured = await _capture(root, repository_id, {".java": "java"})
    analyzer = await asyncio.to_thread(
        JavaSemanticAnalyzer,
        tuple(s for s in captured.sources if s.file.language == "java"),
        dialect,
    )
    return await index_incremental(
        conn,
        repository_id,
        root,
        analyzer,
        languages={".java": "java"},
        analysis_version=analyzer.analysis_version,
    )
