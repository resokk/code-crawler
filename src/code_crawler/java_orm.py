"""JPA mappings, persistence intents and native/JPQL query execution."""

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
from code_crawler.java_calls import _Class, _File
from code_crawler.java_database import JavaDatabaseAnalyzer
from code_crawler.java_semantic import _envelope, _relation
from code_crawler.java_sql import _recover
from code_crawler.jpa_catalog import JpaCatalog, QueryDefinition, qualify_jpa
from code_crawler.jpa_flow import JpaFlow, OrmCall, QueryHandle
from code_crawler.jpql import JpqlAnalysis, analyze_jpql
from code_crawler.orm_native import native_facts
from code_crawler.ucm import (
    Coverage,
    DataAccess,
    DatabaseAccess,
    DatabaseContext,
    DatabaseObject,
    EntityRef,
    EntityType,
    Evidence,
    Operation,
    OrmOperation,
    OrmQuery,
    RelationKind,
    Resolution,
    SqlExecute,
    TypeRef,
)


def _resolved(
    targets: tuple[EntityRef, ...], reason: str, partial: bool = False
) -> Resolution:
    if len(targets) == 1 and not partial:
        return Resolution(status="RESOLVED", target=targets[0])
    return Resolution(
        status="PARTIAL"
        if partial and targets
        else "AMBIGUOUS"
        if targets
        else "UNRESOLVED",
        candidates=targets,
        reason=reason,
    )


class JavaOrmAnalyzer(JavaDatabaseAnalyzer):
    """Interpret logical ORM mappings and typed persistence API calls conservatively."""

    def __init__(
        self,
        sources: tuple[SourceInput, ...],
        schemas: tuple[SchemaImport, ...] = (),
        assignments: tuple[ConnectionAssignment, ...] = (),
        dialect: str = "postgres",
        naming_policy: str = "UNKNOWN",
    ) -> None:
        if naming_policy not in ("UNKNOWN", "IDENTITY"):
            raise ValueError("unsupported ORM physical naming policy")
        super().__init__(sources, schemas, assignments, dialect)
        self.naming_policy = naming_policy
        self.jpa = JpaCatalog(self)
        self._base_cache = {}
        self._native_cache = {}
        self.orm_coverage = Coverage(
            capability="jpa.orm.semantic",
            analyzer_version="1",
            status="PARTIAL",
            reasons=(
                "repository annotation/type catalog; persistence-unit registration/runtime state are not proved",
                "inheritance/secondary/embedded/relationship effects, naming transforms, cascades and JPA binding lineage are incomplete",
            ),
        )
        payload = json.dumps(
            [
                naming_policy,
                sorted(m.model_dump_json() for m in self.jpa.mappings.values()),
                sorted(d.query.model_dump_json() for d in self.jpa.queries.values()),
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.analysis_version = (
            "java.jpa/1:"
            + hashlib.sha256(payload.encode()).hexdigest()
            + ":"
            + self.analysis_version
        )

    def qualify(self, name: str, file: _File, owner: _Class) -> str | None:
        return qualify_jpa(self, name, file, owner)

    def _base(self, file: _File) -> FileAnalysis:
        path = file.source.file.path
        if path not in self._base_cache:
            self._base_cache[path] = JavaDatabaseAnalyzer.analysis(self, file)
        return self._base_cache[path]

    def _native(self, definition: QueryDefinition) -> tuple:
        key = definition.query.id
        if key not in self._native_cache:
            owner = next(
                e
                for e in definition.file.result.analysis.entities
                if e.id == definition.query.owner_symbol_id
            )
            self._native_cache[key] = native_facts(
                definition.file,
                owner,
                definition.value,
                definition.value_node,
                self._base(definition.file).entities,
                self.orm_coverage,
                self.semantic_coverage,
                self.dialect,
            )
        return self._native_cache[key]

    def _query(self, handle: QueryHandle) -> QueryDefinition:
        value = handle.value
        text = value.text.strip() if value and value.text.strip() else None
        reasons = []
        if handle.kind == "CRITERIA":
            reasons.append("Criteria API is outside the JPQL/string profile")
        elif text is None or value.partial:
            reasons.append("query text/name is not fully recovered")
        payload = json.dumps(
            [
                handle.kind,
                text,
                value.partial if value else True,
                value.reasons if value else (),
            ],
            ensure_ascii=False,
        )
        key = (
            handle.site.occurrence.logical_key
            + ":jpa-query:"
            + hashlib.sha256(payload.encode()).hexdigest()
        )
        query = OrmQuery(
            **_envelope(
                handle.site.occurrence.repository_id,
                EntityType.ORM_QUERY,
                key,
                handle.kind,
                handle.site.file.result._extractor.range(handle.site.node),
            ),
            owner_symbol_id=handle.site.caller.symbol.id,
            query_kind=handle.kind,
            query_name=text if handle.kind == "NAMED_REFERENCE" else None,
            text=text if handle.kind in ("JPQL", "NATIVE") else None,
            status="UNSUPPORTED"
            if handle.kind == "CRITERIA"
            else "PARTIAL"
            if reasons
            else "COMPLETE",
            reasons=tuple(reasons),
        )
        return QueryDefinition(query, handle.site.file, handle.value_node, value)

    def _expanded(self, definition: QueryDefinition) -> tuple[QueryDefinition, ...]:
        return (
            tuple(self.jpa.named.get(definition.query.query_name, ()))
            if definition.query.query_kind == "NAMED_REFERENCE"
            else (definition,)
        )

    def _jpql(self, definition: QueryDefinition) -> JpqlAnalysis | None:
        query = definition.query
        return (
            analyze_jpql(query.text, self.jpa)
            if query.query_kind == "JPQL" and query.text and query.status == "COMPLETE"
            else None
        )

    def analysis(self, file: _File) -> FileAnalysis:
        base = self._base(file)
        facts = {e.id: e for e in base.entities}
        repository = file.source.file.repository_id

        def add(entity) -> None:
            if entity.id not in facts:
                facts[entity.id] = entity

        def relation(key, kind, source, resolution, location, description) -> None:
            evidence = Evidence(
                source_range=location,
                analyzer="jpa.orm",
                analyzer_version="1",
                rule=kind.value.lower(),
                description=description,
            )
            add(
                _relation(
                    repository,
                    key,
                    kind,
                    source,
                    resolution,
                    evidence,
                    self.orm_coverage,
                )
            )

        for mapping in self.jpa.by_file[file.source.file.path]:
            add(mapping)
            relation(
                mapping.logical_key + ":declaration",
                RelationKind.ORM_DECLARES_MAPPING,
                EntityRef(id=mapping.symbol_id, entity_type=EntityType.SYMBOL),
                Resolution(
                    status="RESOLVED",
                    target=EntityRef(id=mapping.id, entity_type=EntityType.ORM_MAPPING),
                ),
                mapping.source_range,
                "Logical JPA annotation/default mapping; physical naming is a separate policy",
            )
            if mapping.mapping_kind == "ATTRIBUTE":
                owner = self.jpa.entity_by_symbol[mapping.owner_symbol_id]
                relation(
                    mapping.logical_key + ":owner",
                    RelationKind.ORM_HAS_ATTRIBUTE,
                    EntityRef(id=owner.id, entity_type=EntityType.ORM_MAPPING),
                    Resolution(
                        status="RESOLVED",
                        target=EntityRef(
                            id=mapping.id, entity_type=EntityType.ORM_MAPPING
                        ),
                    ),
                    mapping.source_range,
                    "Persistent attribute belongs to its entity/access mode",
                )
        handles = []
        calls = []
        for method in self.methods.values():
            if method.owner.file is file:
                constants = file.result._extractor.parsed._constant_scopes.get(
                    method.owner.symbol.qualified_name, {}
                )
                _recover(
                    method.node,
                    constants,
                    True,
                    JpaFlow(self, file, method.node, constants, handles, calls),
                )
        runtime = {id(handle): self._query(handle) for handle in handles}
        definitions = {
            d.query.id: d for d in self.jpa.queries.values() if d.file is file
        }
        definitions.update({d.query.id: d for d in runtime.values()})
        for definition in definitions.values():
            query = definition.query
            jpql = self._jpql(definition)
            if jpql and jpql.status != "COMPLETE":
                query = query.model_copy(
                    update={"status": jpql.status, "reasons": jpql.reasons}
                )
            add(query)
            relation(
                query.logical_key + ":declaration",
                RelationKind.ORM_DECLARES_QUERY,
                EntityRef(id=query.owner_symbol_id, entity_type=EntityType.SYMBOL),
                Resolution(
                    status="RESOLVED",
                    target=EntityRef(id=query.id, entity_type=EntityType.ORM_QUERY),
                ),
                query.source_range,
                "Query declaration/creation is not execution",
            )
            if query.query_kind == "NAMED_REFERENCE":
                targets = tuple(
                    EntityRef(id=d.query.id, entity_type=EntityType.ORM_QUERY)
                    for d in self._expanded(definition)
                )
                relation(
                    query.logical_key + ":named",
                    RelationKind.ORM_NAMED_QUERY,
                    EntityRef(id=query.id, entity_type=EntityType.ORM_QUERY),
                    _resolved(
                        targets,
                        "named query is absent or ambiguous across the repository/persistence units",
                    ),
                    query.source_range,
                    "Named reference resolves to declarations, not a SQL string by name",
                )
            if jpql:
                for index, reference in enumerate(jpql.references):
                    kind = {
                        "ENTITY": RelationKind.ORM_QUERY_ENTITY,
                        "READ": RelationKind.ORM_QUERY_READS_ATTRIBUTE,
                        "WRITE": RelationKind.ORM_QUERY_WRITES_ATTRIBUTE,
                    }[reference.kind]
                    targets = tuple(
                        EntityRef(id=m.id, entity_type=EntityType.ORM_MAPPING)
                        for m in reference.candidates
                    )
                    resolution = _resolved(
                        targets,
                        reference.reason
                        or "ambiguous/incomplete entity/property mapping",
                        any(m.status != "COMPLETE" for m in reference.candidates),
                    )
                    relation(
                        query.logical_key + f":reference:{index}",
                        kind,
                        EntityRef(id=query.id, entity_type=EntityType.ORM_QUERY),
                        resolution,
                        query.source_range,
                        "JPQL name "
                        + reference.name
                        + " is interpreted in the entity/property catalog",
                    )
            if query.query_kind == "NATIVE":
                native, _, _ = self._native(definition)
                for entity in native:
                    add(entity)
        grouped = defaultdict(list)
        for call in calls:
            grouped[call.site.node.start_byte].append(call)
        for _, observations in sorted(grouped.items()):
            call = observations[0]
            site = call.site
            location = file.result._extractor.range(site.node)
            key = site.occurrence.logical_key + ":jpa-operation"
            api = (
                (
                    "jakarta.persistence."
                    if any(
                        (
                            self.receiver(observation.site)[0]
                            or (
                                self.receiver(observation.query.site)[0]
                                if observation.query
                                else None
                            )
                            or ""
                        ).startswith("jakarta.persistence.")
                        for observation in observations
                    )
                    else "javax.persistence."
                )
                + ("Query" if call.kind.startswith("QUERY_") else "EntityManager")
                + "."
                + site.occurrence.name
            )
            captured_queries = {
                runtime[id(o.query)].query.id: runtime[id(o.query)]
                for o in observations
                if o.query is not None
            }
            query_unknown = any(
                o.query is None for o in observations
            ) and call.kind.startswith("QUERY_")
            query_id = (
                next(iter(captured_queries))
                if len(captured_queries) == 1 and not query_unknown
                else None
            )
            context = self._context(file, observations, location, facts)
            inputs = []
            for index, value in enumerate(call.values):
                inputs.append(
                    self._value(
                        file, value, key + f":argument:{index}", facts_list := []
                    ).id
                )
                for entity in facts_list:
                    add(entity)
            operation = Operation(
                **_envelope(
                    repository, EntityType.OPERATION, key + ":call", api, location
                ),
                operation_kind="CALL",
                scope_id=site.occurrence.scope_id,
                input_value_ids=tuple(inputs),
                callee=TypeRef(name=api),
            )
            add(operation)
            effect = {
                "PERSIST": "INSERT",
                "MERGE": "MERGE",
                "REMOVE": "DELETE",
                "FIND": "READ",
                "REFRESH": "READ",
                "GET_REFERENCE": "REFERENCE",
                "FLUSH": "UNKNOWN",
                "QUERY_READ": "READ",
                "QUERY_WRITE": "WRITE",
            }[call.kind]
            orm = OrmOperation(
                **_envelope(
                    repository, EntityType.ORM_OPERATION, key, call.kind, location
                ),
                owner_symbol_id=site.caller.symbol.id,
                call_operation_id=operation.id,
                api=api,
                operation_kind=call.kind,
                effect_kind=effect,
                query_id=query_id,
                context_id=context.id if context else None,
            )
            add(orm)
            relation(
                key + ":owner",
                RelationKind.ORM_INVOKES,
                EntityRef(id=site.caller.symbol.id, entity_type=EntityType.SYMBOL),
                Resolution(
                    status="RESOLVED",
                    target=EntityRef(id=orm.id, entity_type=EntityType.ORM_OPERATION),
                ),
                location,
                "Persistence API invocation intent, not actual flush/commit/database effect",
            )
            selected = {}
            for observation in observations:
                cls = self.classes.get(observation.entity_type)
                mapping = self.jpa.entity_by_symbol.get(cls.symbol.id) if cls else None
                if mapping and mapping.entity_role == "ENTITY":
                    selected[mapping.id] = mapping
            expanded = {}
            for definition in captured_queries.values():
                for target in self._expanded(definition):
                    expanded[target.query.id] = target
                    analysis = self._jpql(target)
                    if analysis:
                        for reference in analysis.references:
                            if reference.kind == "ENTITY":
                                for mapping in reference.candidates:
                                    selected[mapping.id] = mapping
            target_refs = tuple(
                EntityRef(id=m.id, entity_type=EntityType.ORM_MAPPING)
                for m in selected.values()
            )
            relation(
                key + ":entity",
                RelationKind.ORM_TARGET_ENTITY,
                EntityRef(id=orm.id, entity_type=EntityType.ORM_OPERATION),
                _resolved(
                    target_refs,
                    "entity target is unknown/ambiguous or requires unsupported inheritance/state",
                    len(selected) > 1
                    or any(m.status != "COMPLETE" for m in selected.values())
                    or any(o.reasons for o in observations),
                ),
                location,
                "Entity mapping target of persistence intent or JPQL entity reference",
            )
            if call.kind.startswith("QUERY_"):
                refs = tuple(
                    EntityRef(id=qid, entity_type=EntityType.ORM_QUERY)
                    for qid in captured_queries
                )
                relation(
                    key + ":query",
                    RelationKind.ORM_EXECUTES_QUERY,
                    EntityRef(id=orm.id, entity_type=EntityType.ORM_OPERATION),
                    _resolved(
                        refs,
                        "query handle origin is unknown or branch dependent",
                        query_unknown
                        or len(refs) > 1
                        or any(o.reasons for o in observations),
                    ),
                    location,
                    "Terminal query API call; creation alone does not execute",
                )
            db_targets = []
            db_reason = None
            if context is None:
                db_reason = (
                    "EntityManager/query connection context is unknown or ambiguous"
                )
            elif self.naming_policy != "IDENTITY":
                db_reason = "physical ORM naming strategy is unknown; logical names are not physical DB identity"
            else:
                for mapping in selected.values():
                    if mapping.table_name is None:
                        continue
                    access = DataAccess(
                        **_envelope(
                            repository,
                            EntityType.DATA_ACCESS,
                            key + ":logical-table:" + mapping.id,
                            "Logical ORM table",
                            location,
                        ),
                        statement_id=site.occurrence.id,
                        object_kind="TABLE",
                        access_kind="READ",
                        role="orm-intent",
                        catalog_name=mapping.catalog_name,
                        schema_name=mapping.schema_name,
                        table_name=mapping.table_name,
                        binding_status="BOUND",
                        resolution="UNRESOLVED",
                        reason="ORM IDENTITY physical naming profile",
                    )
                    resolution = self._db_match(file, access, context, location, facts)
                    db_targets.extend(
                        resolution.candidates
                        if resolution.target is None
                        else (resolution.target,)
                    )
                    if resolution.status != "RESOLVED" or mapping.status != "COMPLETE":
                        db_reason = resolution.reason or "partial ORM mapping"
            db_targets = tuple({ref.id: ref for ref in db_targets}.values())
            relation(
                key + ":database",
                RelationKind.ORM_DATABASE_TARGET,
                EntityRef(id=orm.id, entity_type=EntityType.ORM_OPERATION),
                _resolved(
                    db_targets,
                    db_reason
                    or "ORM table is absent/ambiguous in the selected context",
                    bool(db_reason),
                ),
                location,
                "Physical object only under explicit context and IDENTITY naming policy",
            )
            native = [d for d in expanded.values() if d.query.query_kind == "NATIVE"]
            if native:
                all_native = len(native) == len(expanded) and not query_unknown
                self._native_execution(
                    file, orm, operation, native, all_native, context, location, facts
                )
        return FileAnalysis(
            path=base.path,
            entities=tuple(facts.values()),
            dependencies=base.dependencies,
        )

    def _context(
        self, file: _File, calls: list[OrmCall], location, facts: dict
    ) -> DatabaseContext | None:
        symbols = {
            e.id: e for e in file.result.analysis.entities if hasattr(e, "symbol_kind")
        }
        contexts = {}
        for call in calls:
            symbol = symbols.get(call.connection_symbol_id)
            selected = self.assignments.get(symbol.logical_key) if symbol else None
            if selected is None:
                return None
            contexts[selected.model_dump_json()] = selected
        if len(contexts) != 1:
            return None
        selected = next(iter(contexts.values()))
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
                file.source.file.repository_id,
                EntityType.DATABASE_CONTEXT,
                key,
                selected.connection_key,
                location,
            ),
            projection_file_id=file.source.file.id,
            connection_key=selected.connection_key,
            database_key=selected.database_key,
            version_key=selected.version_key,
            schema_fingerprint=document.fingerprint,
            search_path=selected.search_path,
        )
        facts.setdefault(context.id, context)
        return facts[context.id]

    def _db_match(
        self,
        file: _File,
        access: DataAccess,
        context: DatabaseContext,
        location,
        facts: dict,
    ) -> Resolution:
        document = self.schemas[context.database_key, context.version_key]
        selected = ConnectionContext(
            connection_key=context.connection_key,
            database_key=context.database_key,
            version_key=context.version_key,
            search_path=context.search_path,
        )
        match = resolve_access(document, selected, access, self.dialect)
        refs = []
        for obj in match.candidates:
            key = json.dumps(
                ["database.object", file.source.file.id, obj.object_key],
                separators=(",", ":"),
            )
            projected = DatabaseObject(
                **_envelope(
                    file.source.file.repository_id,
                    EntityType.DATABASE_OBJECT,
                    key,
                    obj.column_name or obj.table_name or obj.schema_name,
                    location,
                ),
                projection_file_id=file.source.file.id,
                database_key=document.database_key,
                version_key=document.version_key,
                schema_fingerprint=document.fingerprint,
                object_key=obj.object_key,
                object_kind=obj.object_kind,
                catalog_name=document.catalog_name,
                schema_name=obj.schema_name,
                table_name=obj.table_name,
                column_name=obj.column_name,
            )
            facts.setdefault(projected.id, projected)
            refs.append(
                EntityRef(id=projected.id, entity_type=EntityType.DATABASE_OBJECT)
            )
        return (
            Resolution(status="RESOLVED", target=refs[0])
            if match.status == "RESOLVED"
            else Resolution(
                status=match.status, candidates=tuple(refs), reason=match.reason
            )
        )

    def _native_execution(
        self,
        file: _File,
        orm: OrmOperation,
        operation: Operation,
        definitions: list[QueryDefinition],
        definite: bool,
        context: DatabaseContext | None,
        location,
        facts: dict,
    ) -> None:
        repository = file.source.file.repository_id
        key = orm.logical_key + ":native-sql"
        execution = SqlExecute(
            **_envelope(
                repository, EntityType.SQL_EXECUTE, key, "JPA native SQL", location
            ),
            owner_symbol_id=orm.owner_symbol_id,
            operation_id=operation.id,
            api=operation.callee.name,
            sql_argument_index=None,
        )
        facts[execution.id] = execution
        evidence = Evidence(
            source_range=location,
            analyzer="jpa.orm",
            analyzer_version="1",
            rule="native-query-terminal",
            description="Terminal call with captured native-query domain; JPQL is not physical SQL",
        )

        def relation(suffix, kind, source, resolution):
            r = _relation(
                repository,
                key + suffix,
                kind,
                source,
                resolution,
                evidence,
                self.orm_coverage,
            )
            facts[r.id] = r

        target = EntityRef(id=execution.id, entity_type=EntityType.SQL_EXECUTE)
        relation(
            ":owner",
            RelationKind.EXECUTES_SQL,
            EntityRef(id=orm.owner_symbol_id, entity_type=EntityType.SYMBOL),
            _resolved((target,), "query domain/origin is partial", not definite),
        )
        constructions = {}
        statements = {}
        for definition in definitions:
            _, construction, parsed = self._native(definition)
            if construction:
                constructions[construction.id] = construction
                statements.update({s.id: s for s in parsed})
        refs = tuple(
            EntityRef(id=c.id, entity_type=EntityType.SQL_CONSTRUCTION)
            for c in constructions.values()
        )
        usage = _resolved(
            refs,
            "native SQL construction is unknown/ambiguous/partial",
            not definite
            or any(
                len(c.variants) != 1 or any(v.partial for v in c.variants)
                for c in constructions.values()
            ),
        )
        relation(
            ":construction",
            RelationKind.USES_SQL_CONSTRUCTION,
            EntityRef(id=execution.id, entity_type=EntityType.SQL_EXECUTE),
            usage,
        )
        for statement in statements.values():
            ref = EntityRef(id=statement.id, entity_type=EntityType.SQL_STATEMENT)
            resolution = _resolved(
                (ref,),
                "native SQL statement/origin is incomplete",
                usage.status != "RESOLVED" or statement.parse_status != "COMPLETE",
            )
            relation(
                ":statement:" + statement.id,
                RelationKind.EXECUTES_STATEMENT,
                EntityRef(id=execution.id, entity_type=EntityType.SQL_EXECUTE),
                resolution,
            )
        if not statements:
            relation(
                ":statement",
                RelationKind.EXECUTES_STATEMENT,
                EntityRef(id=execution.id, entity_type=EntityType.SQL_EXECUTE),
                Resolution(
                    status="UNRESOLVED",
                    reason="native SQL text/statement origin is unknown",
                ),
            )
        relation(
            ":context",
            RelationKind.USES_DATABASE_CONTEXT,
            EntityRef(id=execution.id, entity_type=EntityType.SQL_EXECUTE),
            Resolution(
                status="RESOLVED",
                target=EntityRef(
                    id=context.id, entity_type=EntityType.DATABASE_CONTEXT
                ),
            )
            if context
            else Resolution(
                status="UNRESOLVED", reason="native EntityManager context is unknown"
            ),
        )
        accesses = []
        for definition in definitions:
            new, _, _ = self._native(definition)
            accesses.extend(
                e
                for e in (*self._base(definition.file).entities, *new)
                if isinstance(e, DataAccess) and e.statement_id in statements
            )
        for access in {a.id: a for a in accesses}.values():
            access_key = json.dumps(
                [
                    "database.access",
                    access.id,
                    execution.id,
                    context.id if context else None,
                ],
                separators=(",", ":"),
            )
            contextual = DatabaseAccess(
                **_envelope(
                    repository,
                    EntityType.DATABASE_ACCESS,
                    access_key,
                    "Native query database access",
                    location,
                ),
                access_id=access.id,
                context_id=context.id if context else None,
                execution_id=execution.id,
            )
            facts[contextual.id] = contextual
            for suffix, kind, source, resolution in (
                (
                    ":access",
                    RelationKind.CONTEXTUALIZES_ACCESS,
                    EntityRef(id=access.id, entity_type=EntityType.DATA_ACCESS),
                    Resolution(
                        status="RESOLVED",
                        target=EntityRef(
                            id=contextual.id, entity_type=EntityType.DATABASE_ACCESS
                        ),
                    ),
                ),
                (
                    ":context",
                    RelationKind.IN_DATABASE_CONTEXT,
                    EntityRef(id=contextual.id, entity_type=EntityType.DATABASE_ACCESS),
                    Resolution(
                        status="RESOLVED",
                        target=EntityRef(
                            id=context.id, entity_type=EntityType.DATABASE_CONTEXT
                        ),
                    )
                    if context
                    else Resolution(
                        status="UNRESOLVED",
                        reason="native connection context is unknown",
                    ),
                ),
                (
                    ":object",
                    RelationKind.RESOLVES_DATABASE_OBJECT,
                    EntityRef(id=contextual.id, entity_type=EntityType.DATABASE_ACCESS),
                    self._db_match(file, access, context, location, facts)
                    if context
                    else Resolution(
                        status="UNRESOLVED",
                        reason="native connection context is unknown",
                    ),
                ),
            ):
                r = _relation(
                    repository,
                    access_key + suffix,
                    kind,
                    source,
                    resolution,
                    evidence,
                    self.orm_coverage,
                )
                facts[r.id] = r


async def index_java_orm(
    conn: asyncpg.Connection,
    repository_id: UUID,
    root: Path,
    assignments: tuple[ConnectionAssignment, ...] = (),
    dialect: str = "postgres",
    naming_policy: str = "UNKNOWN",
) -> IncrementalResult:
    """Build JPA semantic facts in a BUILDING snapshot; caller validates/publishes."""
    schemas = []
    for key, version in sorted(
        {(a.context.database_key, a.context.version_key) for a in assignments}
    ):
        schemas.append(await load_schema(conn, key, version))
    root = await asyncio.to_thread(root.resolve, strict=True)
    captured = await _capture(root, repository_id, {".java": "java"})
    analyzer = await asyncio.to_thread(
        JavaOrmAnalyzer,
        tuple(s for s in captured.sources if s.file.language == "java"),
        tuple(schemas),
        assignments,
        dialect,
        naming_policy,
    )
    return await index_incremental(
        conn,
        repository_id,
        root,
        analyzer,
        languages={".java": "java"},
        analysis_version=analyzer.analysis_version,
    )
