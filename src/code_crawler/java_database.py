"""Opt-in contextual SQL database identity without implicit connection guessing."""

import asyncio
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from uuid import UUID

import asyncpg

from code_crawler.database_resolution import (
    ConnectionAssignment,
    ConnectionContext,
    resolve_access,
)
from code_crawler.database_schema import SchemaImport, load_schema
from code_crawler.incremental import (
    FileAnalysis,
    IncrementalResult,
    SourceInput,
    _capture,
    index_incremental,
)
from code_crawler.java_calls import _File
from code_crawler.java_execution import _ExecutionFlow
from code_crawler.java_lineage import JavaLineageAnalyzer
from code_crawler.java_semantic import _envelope, _relation
from code_crawler.java_sql import _recover
from code_crawler.ucm import (
    Coverage,
    DataAccess,
    DatabaseAccess,
    DatabaseContext,
    DatabaseObject,
    EntityRef,
    EntityType,
    Evidence,
    Relation,
    RelationKind,
    Resolution,
    SqlExecute,
    Symbol,
)


class JavaDatabaseAnalyzer(JavaLineageAnalyzer):
    """Resolve accesses using explicit symbol assignments and immutable inventories."""

    def __init__(
        self,
        sources: tuple[SourceInput, ...],
        schemas: tuple[SchemaImport, ...],
        assignments: tuple[ConnectionAssignment, ...],
        dialect: str = "postgres",
    ) -> None:
        super().__init__(sources, dialect)
        self.schemas = {(s.database_key, s.version_key): s for s in schemas}
        if len(self.schemas) != len(schemas):
            raise ValueError("duplicate database schema version")
        self.schema_fingerprints = {
            key: document.fingerprint for key, document in self.schemas.items()
        }
        self.assignments = {a.symbol_key: a.context for a in assignments}
        if len(self.assignments) != len(assignments):
            raise ValueError("duplicate Java connection symbol assignment")
        symbols = {
            e.logical_key: e
            for file in self.files.values()
            for e in file.result.analysis.entities
            if isinstance(e, Symbol)
        }
        for assignment in assignments:
            if assignment.symbol_key not in symbols:
                raise ValueError(
                    "connection assignment references unknown Java symbol key"
                )
            context = assignment.context
            if (context.database_key, context.version_key) not in self.schemas:
                raise ValueError(
                    "connection assignment requires its explicit imported schema version"
                )
        fingerprint = json.dumps(
            [
                sorted((s.database_key, s.version_key, s.fingerprint) for s in schemas),
                sorted(a.model_dump_json() for a in assignments),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.analysis_version = (
            "java.database/1:"
            + hashlib.sha256(fingerprint.encode()).hexdigest()
            + ":"
            + self.analysis_version
        )
        self.database_coverage = Coverage(
            capability="database.schema.identity",
            analyzer_version="1",
            status="PARTIAL",
            reasons=(
                "explicit connection-symbol assignments; runtime datasource routing is not inferred",
                "imported version/case/search-path policies; live DB state and vendor collations are not verified",
            ),
        )

    def analysis(self, file: _File) -> FileAnalysis:
        base = super().analysis(file)
        entities = list(base.entities)
        catalog = {e.id: e for e in base.entities}
        repository = file.source.file.repository_id
        symbols = {
            e.id: e for e in file.result.analysis.entities if isinstance(e, Symbol)
        }
        events = []
        for method in self.methods.values():
            if method.owner.file is file:
                constants = file.result._extractor.parsed._constant_scopes.get(
                    method.owner.symbol.qualified_name, {}
                )
                _recover(
                    method.node,
                    constants,
                    True,
                    _ExecutionFlow(self, file, method.node, constants, events),
                )
        contexts: dict[str, DatabaseContext] = {}
        execution_contexts = defaultdict(dict)
        executions = {
            (e.source_range.start.line, e.source_range.start.byte_column): e
            for e in base.entities
            if isinstance(e, SqlExecute)
        }
        for event in events:
            point = event.site.node.start_point
            execution = executions.get((point.row + 1, point.column))
            if execution is None:
                continue
            symbol_id = event.handle.connection_symbol_id if event.handle else None
            if symbol_id is None:
                receiver = event.site.node.child_by_field_name("object")
                symbol = (
                    self.data_symbol(receiver, event.site)
                    if receiver is not None
                    else None
                )
                symbol_id = symbol.id if symbol else None
            symbol = symbols.get(symbol_id)
            selected = self.assignments.get(symbol.logical_key) if symbol else None
            if selected is None:
                execution_contexts[execution.id][None] = None
                continue
            document = self.schemas[selected.database_key, selected.version_key]
            key = json.dumps(
                [
                    "database.context",
                    file.source.file.id,
                    selected.connection_key,
                    selected.database_key,
                    selected.version_key,
                    selected.search_path,
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            context = DatabaseContext(
                **_envelope(
                    repository,
                    EntityType.DATABASE_CONTEXT,
                    key,
                    selected.connection_key,
                    execution.source_range,
                ),
                projection_file_id=file.source.file.id,
                connection_key=selected.connection_key,
                database_key=selected.database_key,
                version_key=selected.version_key,
                schema_fingerprint=self.schema_fingerprints[
                    document.database_key, document.version_key
                ],
                search_path=selected.search_path,
            )
            contexts[context.id] = context
            execution_contexts[execution.id][context.id] = context
        entities.extend(contexts.values())
        execution_resolutions = {}
        for execution in executions.values():
            choices = execution_contexts[execution.id] or {None: None}
            refs = tuple(
                EntityRef(id=key, entity_type=EntityType.DATABASE_CONTEXT)
                for key in sorted(k for k in choices if k is not None)
            )
            resolution = (
                Resolution(status="RESOLVED", target=refs[0])
                if len(refs) == 1 and None not in choices
                else Resolution(
                    status="PARTIAL"
                    if refs and None in choices
                    else "AMBIGUOUS"
                    if refs
                    else "UNRESOLVED",
                    candidates=refs,
                    reason="multiple or unknown execution connection origins; explicit symbol assignment is required",
                )
            )
            execution_resolutions[execution.id] = resolution
            evidence = Evidence(
                source_range=execution.source_range,
                analyzer="java.database",
                analyzer_version="1",
                rule="explicit-connection-assignment",
                description="Configured immutable database context selected by connection/statement receiver Symbol logical_key",
            )
            entities.append(
                _relation(
                    repository,
                    execution.logical_key + ":database-context",
                    RelationKind.USES_DATABASE_CONTEXT,
                    EntityRef(id=execution.id, entity_type=EntityType.SQL_EXECUTE),
                    resolution,
                    evidence,
                    self.database_coverage,
                )
            )
        statement_executions = defaultdict(set)
        for relation in base.entities:
            if (
                isinstance(relation, Relation)
                and relation.relation_kind == RelationKind.EXECUTES_STATEMENT
            ):
                refs = (
                    (relation.resolution.target,)
                    if relation.resolution.target
                    else relation.resolution.candidates
                )
                for ref in refs:
                    statement_executions[ref.id].add(relation.source.id)
        objects = {}
        for access in (e for e in base.entities if isinstance(e, DataAccess)):
            owners = sorted(statement_executions[access.statement_id]) or [None]
            for execution_id in owners:
                choices = execution_contexts[execution_id] if execution_id else {}
                choices = choices or {None: None}
                for context_id, context in sorted(
                    choices.items(), key=lambda item: item[0] or ""
                ):
                    key = json.dumps(
                        ["database.access", access.id, execution_id, context_id],
                        separators=(",", ":"),
                    )
                    contextual = DatabaseAccess(
                        **_envelope(
                            repository,
                            EntityType.DATABASE_ACCESS,
                            key,
                            "Contextual database access",
                            access.source_range,
                        ),
                        access_id=access.id,
                        context_id=context_id,
                        execution_id=execution_id,
                    )
                    entities.append(contextual)
                    evidence = Evidence(
                        source_range=access.source_range,
                        analyzer="java.database",
                        analyzer_version="1",
                        rule="schema-version-name-resolution",
                        description="Database identity is resolved only within the configured database/version and ordered search path",
                    )
                    entities.append(
                        _relation(
                            repository,
                            key + ":access",
                            RelationKind.CONTEXTUALIZES_ACCESS,
                            EntityRef(id=access.id, entity_type=EntityType.DATA_ACCESS),
                            Resolution(
                                status="RESOLVED",
                                target=EntityRef(
                                    id=contextual.id,
                                    entity_type=EntityType.DATABASE_ACCESS,
                                ),
                            ),
                            evidence,
                            self.database_coverage,
                        )
                    )
                    context_resolution = (
                        Resolution(
                            status="RESOLVED",
                            target=EntityRef(
                                id=context_id, entity_type=EntityType.DATABASE_CONTEXT
                            ),
                        )
                        if context
                        else Resolution(
                            status="UNRESOLVED",
                            reason="SQL has no assigned execution connection context",
                        )
                    )
                    entities.append(
                        _relation(
                            repository,
                            key + ":context",
                            RelationKind.IN_DATABASE_CONTEXT,
                            EntityRef(
                                id=contextual.id, entity_type=EntityType.DATABASE_ACCESS
                            ),
                            context_resolution,
                            evidence,
                            self.database_coverage,
                        )
                    )
                    if context is None:
                        resolution = Resolution(
                            status="UNRESOLVED",
                            reason="database identity cannot be selected from a table/catalog basename without execution context",
                        )
                    else:
                        document = self.schemas[
                            context.database_key, context.version_key
                        ]
                        selected = ConnectionContext(
                            connection_key=context.connection_key,
                            database_key=context.database_key,
                            version_key=context.version_key,
                            search_path=context.search_path,
                        )
                        match = resolve_access(
                            document,
                            selected,
                            access,
                            catalog[access.statement_id].dialect,
                        )
                        targets = []
                        for obj in match.candidates:
                            object_key = json.dumps(
                                [
                                    "database.object",
                                    file.source.file.id,
                                    obj.object_key,
                                ],
                                separators=(",", ":"),
                            )
                            projected = DatabaseObject(
                                **_envelope(
                                    repository,
                                    EntityType.DATABASE_OBJECT,
                                    object_key,
                                    obj.column_name
                                    or obj.table_name
                                    or obj.schema_name,
                                    access.source_range,
                                ),
                                projection_file_id=file.source.file.id,
                                database_key=document.database_key,
                                version_key=document.version_key,
                                schema_fingerprint=self.schema_fingerprints[
                                    document.database_key, document.version_key
                                ],
                                object_key=obj.object_key,
                                object_kind=obj.object_kind,
                                catalog_name=document.catalog_name,
                                schema_name=obj.schema_name,
                                table_name=obj.table_name,
                                column_name=obj.column_name,
                            )
                            if projected.id not in objects:
                                objects[projected.id] = projected
                            targets.append(
                                EntityRef(
                                    id=projected.id,
                                    entity_type=EntityType.DATABASE_OBJECT,
                                )
                            )
                        definite = (
                            match.status == "RESOLVED"
                            and execution_resolutions[execution_id].status == "RESOLVED"
                        )
                        resolution = (
                            Resolution(status="RESOLVED", target=targets[0])
                            if definite
                            else Resolution(
                                status="PARTIAL" if targets else match.status,
                                candidates=tuple(targets),
                                reason=match.reason
                                or "execution connection origin is ambiguous/partial",
                            )
                        )
                    entities.append(
                        _relation(
                            repository,
                            key + ":object",
                            RelationKind.RESOLVES_DATABASE_OBJECT,
                            EntityRef(
                                id=contextual.id, entity_type=EntityType.DATABASE_ACCESS
                            ),
                            resolution,
                            evidence,
                            self.database_coverage,
                        )
                    )
        entities.extend(objects.values())
        return FileAnalysis(
            path=base.path, entities=tuple(entities), dependencies=base.dependencies
        )


async def index_java_database(
    conn: asyncpg.Connection,
    repository_id: UUID,
    root: Path,
    assignments: tuple[ConnectionAssignment, ...],
    dialect: str = "postgres",
) -> IncrementalResult:
    """Load explicit schema versions and build contextual identities in a BUILDING snapshot."""
    schemas = []
    for database_key, version_key in sorted(
        {(a.context.database_key, a.context.version_key) for a in assignments}
    ):
        schemas.append(await load_schema(conn, database_key, version_key))
    root = await asyncio.to_thread(root.resolve, strict=True)
    captured = await _capture(root, repository_id, {".java": "java"})
    analyzer = await asyncio.to_thread(
        JavaDatabaseAnalyzer,
        tuple(s for s in captured.sources if s.file.language == "java"),
        tuple(schemas),
        assignments,
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
