"""Closed UCM batches and transactional two-pass staging/COPY ingestion."""

import asyncio
import json
from collections import defaultdict
from uuid import UUID, uuid4

import asyncpg
from pydantic import model_validator

from code_crawler.ucm import (
    CodeEntity,
    ContractModel,
    DataAccess,
    DatabaseSelector,
    Entity,
    ExternalReference,
    HttpSelector,
    Occurrence,
    Operation,
    Relation,
    RelationKind,
    Scope,
    SourceFile,
    SourceRange,
    SqlConstruction,
    SqlExecute,
    SqlStatement,
    Symbol,
    SymbolSelector,
    TypeRef,
    Value,
    validate_external_reference,
    validate_relation_endpoints,
)


class UcmBatch(ContractModel):
    repository_id: UUID
    entities: tuple[Entity, ...]

    @model_validator(mode="after")
    def valid_references(self) -> "UcmBatch":
        catalog = {entity.id: entity for entity in self.entities}
        if len(catalog) != len(self.entities):
            raise ValueError("duplicate batch entity ID")
        paths: set[str] = set()
        producers: set[str] = set()

        def require(entity_id: str | None, kind: type) -> None:
            if entity_id is not None and not isinstance(catalog.get(entity_id), kind):
                raise ValueError(
                    f"missing or wrongly typed {kind.__name__} reference: {entity_id}"
                )

        def type_ref(ref: TypeRef | None) -> None:
            if ref is not None:
                require(ref.target_symbol_id, Symbol)

        for entity in self.entities:
            if entity.repository_id != str(self.repository_id):
                raise ValueError("batch entity belongs to a different repository")
            if entity.source_range is not None:
                require(entity.source_range.source_file_id, SourceFile)
            if isinstance(entity, SourceFile):
                if entity.path in paths:
                    raise ValueError("duplicate source file path")
                paths.add(entity.path)
            elif isinstance(entity, Symbol):
                require(entity.scope_id, Scope)
                type_ref(entity.type_ref)
                if entity.signature is not None:
                    for ref in entity.signature.parameter_types:
                        type_ref(ref)
                    type_ref(entity.signature.return_type)
            elif isinstance(entity, Scope):
                require(entity.parent_scope_id, Scope)
                require(entity.owner_symbol_id, Symbol)
            elif isinstance(entity, Occurrence):
                require(entity.scope_id, Scope)
                require(entity.target_symbol_id, Symbol)
            elif isinstance(entity, Operation):
                require(entity.scope_id, Scope)
                type_ref(entity.callee)
                for value_id in (*entity.input_value_ids, *entity.output_value_ids):
                    require(value_id, Value)
                for value_id in entity.output_value_ids:
                    if value_id in producers:
                        raise ValueError("value has multiple producers")
                    producers.add(value_id)
            elif isinstance(entity, Value):
                type_ref(entity.type_ref)
            elif isinstance(entity, SqlStatement):
                candidate = catalog.get(entity.candidate_id)
                if candidate is None or candidate.entity_type.value != "SQL_CANDIDATE":
                    raise ValueError("SQL statement requires local SQL candidate")
            elif isinstance(entity, DataAccess):
                require(entity.statement_id, SqlStatement)
                if catalog[entity.statement_id].parse_status not in (
                    "COMPLETE",
                    "PARTIAL",
                ):
                    raise ValueError("failed SQL statement cannot assert accesses")
            elif isinstance(entity, SqlExecute):
                require(entity.owner_symbol_id, Symbol)
                require(entity.operation_id, Operation)
                owner = catalog[entity.owner_symbol_id]
                operation = catalog[entity.operation_id]
                if owner.symbol_kind not in ("METHOD", "CONSTRUCTOR"):
                    raise ValueError("SQL execution owner must be callable")
                if operation.operation_kind != "CALL":
                    raise ValueError("SQL execution requires CALL operation")
                if operation.callee is None or operation.callee.name != entity.api:
                    raise ValueError("SQL execution API must match CALL callee")
                scope = catalog.get(operation.scope_id)
                visited: set[str] = set()
                callable_owner = None
                while isinstance(scope, Scope) and scope.id not in visited:
                    visited.add(scope.id)
                    symbol = catalog.get(scope.owner_symbol_id)
                    if isinstance(symbol, Symbol) and symbol.symbol_kind in (
                        "METHOD",
                        "CONSTRUCTOR",
                    ):
                        callable_owner = symbol.id
                        break
                    scope = catalog.get(scope.parent_scope_id)
                if callable_owner != entity.owner_symbol_id:
                    raise ValueError("SQL execution CALL must be in its owner scope")
                if (
                    entity.sql_argument_index is not None
                    and entity.sql_argument_index >= len(operation.input_value_ids)
                ):
                    raise ValueError("SQL execution argument index outside CALL inputs")
            elif isinstance(entity, SqlConstruction):
                require(entity.owner_symbol_id, Symbol)
                if catalog[entity.owner_symbol_id].symbol_kind not in (
                    "CLASS",
                    "METHOD",
                    "CONSTRUCTOR",
                ):
                    raise ValueError(
                        "SQL construction owner must be a type or callable"
                    )
                for variant in entity.variants:
                    candidate = catalog.get(variant.candidate_id)
                    if (
                        candidate is None
                        or candidate.entity_type.value != "SQL_CANDIDATE"
                    ):
                        raise ValueError("SQL variant requires local SQL_CANDIDATE")
                    for fragment in variant.fragments:
                        if fragment.source_range is not None:
                            require(fragment.source_range.source_file_id, SourceFile)
            elif isinstance(entity, Relation):
                validate_relation_endpoints(entity, catalog)
            elif isinstance(entity, ExternalReference):
                validate_external_reference(entity, catalog)
        sql_candidates = [
            variant.candidate_id
            for e in self.entities
            if isinstance(e, SqlConstruction)
            for variant in e.variants
        ]
        if len(set(sql_candidates)) != len(sql_candidates):
            raise ValueError("SQL candidate has multiple construction owners")
        variants = {
            v.candidate_id: v
            for e in self.entities
            if isinstance(e, SqlConstruction)
            for v in e.variants
        }
        statement_keys: set[tuple[str, int]] = set()
        for entity in self.entities:
            if not isinstance(entity, SqlStatement):
                continue
            key = (entity.candidate_id, entity.statement_index)
            if key in statement_keys:
                raise ValueError("duplicate SQL statement position")
            statement_keys.add(key)
            variant = variants.get(entity.candidate_id)
            if (
                variant is None
                or variant.text[entity.text_start : entity.text_end] != entity.text
            ):
                raise ValueError("SQL statement text must match candidate slice")
            if variant.partial and entity.parse_status != "PARTIAL":
                raise ValueError(
                    "partial SQL construction cannot assert complete semantics"
                )
            if variant.partial and any(
                isinstance(a, DataAccess) and a.statement_id == entity.id
                for a in self.entities
            ):
                raise ValueError("partial SQL construction cannot assert accesses")
        usages = {
            e.source.id: e
            for e in self.entities
            if isinstance(e, Relation)
            and e.relation_kind == RelationKind.USES_SQL_CONSTRUCTION
        }
        for relation in self.entities:
            if (
                not isinstance(relation, Relation)
                or relation.relation_kind != RelationKind.EXECUTES_STATEMENT
            ):
                continue
            targets = (
                (relation.resolution.target,)
                if relation.resolution.target
                else relation.resolution.candidates
            )
            usage = usages.get(relation.source.id)
            origins = (
                (
                    (usage.resolution.target,)
                    if usage.resolution.target
                    else usage.resolution.candidates
                )
                if usage
                else ()
            )
            allowed = {
                variant.candidate_id
                for ref in origins
                for variant in catalog[ref.id].variants
            }
            for ref in targets:
                statement = catalog[ref.id]
                if statement.candidate_id not in allowed:
                    raise ValueError(
                        "execution statement must originate in its SQL construction"
                    )
                if relation.resolution.status == "RESOLVED" and (
                    usage.resolution.status != "RESOLVED"
                    or len(allowed) != 1
                    or statement.parse_status != "COMPLETE"
                ):
                    raise ValueError(
                        "definite execution statement requires complete unambiguous origin"
                    )
        checked: set[str] = set()
        for entity in self.entities:
            if not isinstance(entity, Scope):
                continue
            visiting: set[str] = set()
            current: Scope | None = entity
            while current is not None and current.id not in checked:
                if current.id in visiting:
                    raise ValueError("cyclic parent_scope references")
                visiting.add(current.id)
                current = catalog.get(current.parent_scope_id)
            checked.update(visiting)
        return self


def _range(source_range: SourceRange | None) -> tuple:
    if source_range is None:
        return (None,) * 5
    return (
        source_range.source_file_id,
        source_range.start.line,
        source_range.start.byte_column,
        source_range.end.line,
        source_range.end.byte_column,
    )


def _records(snapshot_id: UUID, batch: UcmBatch) -> dict[str, list[dict]]:
    # Reparse JSON so even instances built via model_construct/model_copy are checked.
    batch = UcmBatch.model_validate_json(batch.model_dump_json())
    rows: dict[str, list[dict]] = defaultdict(list)

    def add(table: str, **fields: object) -> None:
        rows[table].append({"snapshot_id": snapshot_id, **fields})

    def add_type(owner: str, role: str, ref: TypeRef | None, position: int = 0) -> None:
        if ref is not None:
            add(
                "ucm_type_refs",
                owner_id=owner,
                role=role,
                position=position,
                name=ref.name,
                resolution=ref.resolution,
                target_symbol_id=ref.target_symbol_id,
            )

    for entity in batch.entities:
        file_id, start_line, start_column, end_line, end_column = _range(
            entity.source_range
        )
        add(
            "ucm_entities",
            entity_id=entity.id,
            repository_id=batch.repository_id,
            contract_version=entity.contract_version,
            entity_type=entity.entity_type.value,
            logical_key=entity.logical_key,
            name=entity.name,
            source_file_id=file_id,
            start_line=start_line,
            start_byte_column=start_column,
            end_line=end_line,
            end_byte_column=end_column,
        )
        base = {"entity_id": entity.id, "entity_type": entity.entity_type.value}
        if isinstance(entity, SourceFile):
            add(
                "ucm_source_files",
                **base,
                path=entity.path,
                language=entity.language,
                content_sha256=entity.content_sha256,
            )
        elif isinstance(entity, Symbol):
            add(
                "ucm_symbols",
                **base,
                symbol_kind=entity.symbol_kind,
                qualified_name=entity.qualified_name,
                scope_id=entity.scope_id,
                owner_key=entity.owner_key,
            )
            add_type(entity.id, "TYPE", entity.type_ref)
            if entity.signature is not None:
                for position, ref in enumerate(entity.signature.parameter_types):
                    add_type(entity.id, "PARAMETER", ref, position)
                add_type(entity.id, "RETURN", entity.signature.return_type)
        elif isinstance(entity, Scope):
            add(
                "ucm_scopes",
                **base,
                scope_kind=entity.scope_kind,
                parent_scope_id=entity.parent_scope_id,
                owner_symbol_id=entity.owner_symbol_id,
            )
        elif isinstance(entity, Occurrence):
            add(
                "ucm_occurrences",
                **base,
                occurrence_kind=entity.occurrence_kind,
                scope_id=entity.scope_id,
                resolution=entity.resolution,
                target_symbol_id=entity.target_symbol_id,
            )
        elif isinstance(entity, Value):
            add(
                "ucm_values",
                **base,
                value_kind=entity.value_kind,
                partial=entity.partial,
                literal=json.dumps(entity.literal, ensure_ascii=False, allow_nan=False)
                if entity.value_kind == "LITERAL"
                else None,
            )
            add_type(entity.id, "TYPE", entity.type_ref)
        elif isinstance(entity, Operation):
            add(
                "ucm_operations",
                **base,
                operation_kind=entity.operation_kind,
                scope_id=entity.scope_id,
            )
            add_type(entity.id, "CALLEE", entity.callee)
            for direction, values in (
                ("INPUT", entity.input_value_ids),
                ("OUTPUT", entity.output_value_ids),
            ):
                for position, value_id in enumerate(values):
                    add(
                        "ucm_operation_values",
                        operation_id=entity.id,
                        direction=direction,
                        position=position,
                        value_id=value_id,
                    )
        elif isinstance(entity, SqlStatement):
            add(
                "ucm_sql_statements",
                **base,
                candidate_id=entity.candidate_id,
                statement_index=entity.statement_index,
                dialect=entity.dialect,
                text=entity.text,
                text_start=entity.text_start,
                text_end=entity.text_end,
                operation=entity.operation,
                parse_status=entity.parse_status,
            )
            for ordinal, reason in enumerate(entity.reasons):
                add(
                    "ucm_sql_statement_reasons",
                    statement_id=entity.id,
                    ordinal=ordinal,
                    reason=reason,
                )
        elif isinstance(entity, DataAccess):
            add(
                "ucm_data_accesses",
                **base,
                statement_id=entity.statement_id,
                object_kind=entity.object_kind,
                access_kind=entity.access_kind,
                role=entity.role,
                binding_status=entity.binding_status,
                resolution=entity.resolution,
                reason=entity.reason,
            )
            for part in (
                "catalog_name",
                "schema_name",
                "table_name",
                "column_name",
                "qualifier",
            ):
                identifier = getattr(entity, part)
                if identifier is not None:
                    add(
                        "ucm_sql_access_names",
                        access_id=entity.id,
                        part=part,
                        text=identifier.text,
                        quoted=identifier.quoted,
                        normalized=identifier.normalized,
                    )
        elif isinstance(entity, SqlExecute):
            add(
                "ucm_sql_executions",
                **base,
                owner_symbol_id=entity.owner_symbol_id,
                operation_id=entity.operation_id,
                api=entity.api,
                sql_argument_index=entity.sql_argument_index,
            )
        elif isinstance(entity, SqlConstruction):
            add("ucm_sql_constructions", **base, owner_symbol_id=entity.owner_symbol_id)
            for position, variant in enumerate(entity.variants):
                add(
                    "ucm_sql_variants",
                    construction_id=entity.id,
                    candidate_id=variant.candidate_id,
                    candidate_type="SQL_CANDIDATE",
                    position=position,
                    text=variant.text,
                    partial=variant.partial,
                )
                for ordinal, reason in enumerate(variant.partial_reasons):
                    add(
                        "ucm_sql_partial_reasons",
                        candidate_id=variant.candidate_id,
                        ordinal=ordinal,
                        reason=reason,
                    )
                for ordinal, fragment in enumerate(variant.fragments):
                    f, sl, sc, el, ec = _range(fragment.source_range)
                    add(
                        "ucm_sql_fragments",
                        candidate_id=variant.candidate_id,
                        ordinal=ordinal,
                        kind=fragment.kind,
                        text=fragment.text,
                        source_file_id=f,
                        start_line=sl,
                        start_byte_column=sc,
                        end_line=el,
                        end_byte_column=ec,
                    )
        elif isinstance(entity, Relation):
            target = entity.resolution.target
            add(
                "ucm_relations",
                **base,
                relation_kind=entity.relation_kind.value,
                source_id=entity.source.id,
                source_type=entity.source.entity_type.value,
                target_id=target.id if target else None,
                target_type=target.entity_type.value if target else None,
                resolution=entity.resolution.status,
                reason=entity.resolution.reason,
                **_coverage(entity),
            )
            for candidate in entity.resolution.candidates:
                add(
                    "ucm_relation_candidates",
                    relation_id=entity.id,
                    relation_kind=entity.relation_kind.value,
                    source_type=entity.source.entity_type.value,
                    candidate_id=candidate.id,
                    candidate_type=candidate.entity_type.value,
                )
        elif isinstance(entity, ExternalReference):
            selector = entity.selector
            fields = dict.fromkeys(
                (
                    "qualified_name",
                    "parameter_type_names",
                    "http_method",
                    "http_path",
                    "service",
                    "connection",
                    "schema_name",
                    "table_name",
                )
            )
            if isinstance(selector, SymbolSelector):
                fields.update(
                    qualified_name=selector.qualified_name,
                    parameter_type_names=list(selector.parameter_type_names)
                    if selector.parameter_type_names is not None
                    else None,
                )
            elif isinstance(selector, HttpSelector):
                fields.update(
                    http_method=selector.method,
                    http_path=selector.path,
                    service=selector.service,
                )
            elif isinstance(selector, DatabaseSelector):
                fields.update(
                    connection=selector.connection,
                    schema_name=selector.schema_name,
                    table_name=selector.table,
                )
            add(
                "ucm_external_references",
                **base,
                source_id=entity.source.id,
                source_type=entity.source.entity_type.value,
                selector_kind=selector.kind,
                **fields,
                repository_hint=entity.repository_hint,
                version_hint=entity.version_hint,
                resolution=entity.resolution,
                reason=entity.reason,
                **_coverage(entity),
            )
        elif not isinstance(entity, CodeEntity):
            raise TypeError("unsupported entity type")
        if isinstance(entity, (Relation, ExternalReference)):
            for ordinal, evidence in enumerate(entity.evidence):
                f, sl, sc, el, ec = _range(evidence.source_range)
                add(
                    "ucm_evidence",
                    owner_id=entity.id,
                    owner_type=entity.entity_type.value,
                    ordinal=ordinal,
                    source_file_id=f,
                    start_line=sl,
                    start_byte_column=sc,
                    end_line=el,
                    end_byte_column=ec,
                    analyzer=evidence.analyzer,
                    analyzer_version=evidence.analyzer_version,
                    rule=evidence.rule,
                    description=evidence.description,
                )
            for ordinal, reason in enumerate(entity.coverage.reasons):
                add(
                    "ucm_coverage_reasons",
                    owner_id=entity.id,
                    owner_type=entity.entity_type.value,
                    ordinal=ordinal,
                    reason=reason,
                )
    return rows


def _coverage(entity: Relation | ExternalReference) -> dict:
    return {
        "certainty": entity.certainty.value,
        "coverage_capability": entity.coverage.capability,
        "coverage_analyzer_version": entity.coverage.analyzer_version,
        "coverage_status": entity.coverage.status,
    }


async def ingest_batch(
    conn: asyncpg.Connection, snapshot_id: UUID, batch: UcmBatch
) -> dict[str, tuple[UUID, str]]:
    """Load one complete batch into an empty BUILDING snapshot, atomically."""
    if conn.is_in_transaction():
        raise ValueError(
            "ingest_batch requires a connection without an active transaction"
        )
    rows = await asyncio.to_thread(_records, snapshot_id, batch)
    async with conn.transaction():
        await _ingest_records(conn, snapshot_id, batch.repository_id, rows)
    return {entity.id: (snapshot_id, entity.id) for entity in batch.entities}


async def _ingest_records(
    conn: asyncpg.Connection,
    snapshot_id: UUID,
    repository_id: UUID,
    rows: dict[str, list[dict]],
) -> None:
    """Write normalized records inside the caller's transaction."""
    snapshot = await conn.fetchrow(
        "SELECT repository_id,state FROM public.ucm_snapshots WHERE id=$1 FOR UPDATE",
        snapshot_id,
    )
    if snapshot is None or snapshot["repository_id"] != repository_id:
        raise ValueError("snapshot missing or belongs to a different repository")
    if snapshot["state"] != "BUILDING":
        raise ValueError("ingestion requires BUILDING snapshot")
    if await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM public.ucm_entities WHERE snapshot_id=$1)",
        snapshot_id,
    ):
        raise ValueError("ingestion requires an empty snapshot")
    prefix = "ingest_" + uuid4().hex
    stages = {}
    for table, records in rows.items():
        stage = prefix + "_" + table.removeprefix("ucm_")
        stages[table] = stage
        await conn.execute(
            f"CREATE TEMP TABLE {stage} (LIKE public.{table} INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        columns = tuple(records[0])
        await conn.copy_records_to_table(
            stage,
            schema_name="pg_temp",
            columns=columns,
            records=[tuple(row[column] for column in columns) for row in records],
        )
    # Envelope IDs first; deferred FKs allow cyclic subtype references in pass two.
    for table in ["ucm_entities", *(t for t in rows if t != "ucm_entities")]:
        if table not in rows:
            continue
        columns = ",".join(rows[table][0])
        await conn.execute(
            f"INSERT INTO public.{table} ({columns}) SELECT {columns} FROM pg_temp.{stages[table]}"
        )
    await conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
