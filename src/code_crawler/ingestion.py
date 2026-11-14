"""Closed UCM batches and transactional two-pass staging/COPY ingestion."""

import asyncio
import json
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from uuid import UUID, uuid4

import asyncpg
from pydantic import model_validator

from code_crawler.ucm import (
    CodeEntity,
    ContractModel,
    DataAccess,
    DatabaseAccess,
    DatabaseContext,
    DatabaseObject,
    DatabaseSelector,
    Entity,
    ExternalReference,
    HttpSelector,
    Occurrence,
    Operation,
    OrmMapping,
    OrmOperation,
    OrmQuery,
    Relation,
    RelationKind,
    Scope,
    SourceAnalysis,
    SourceFile,
    SourceRange,
    SqlBinding,
    SqlConstruction,
    SqlExecute,
    SqlPlaceholder,
    SqlStatement,
    Symbol,
    SymbolSelector,
    TypeRef,
    Value,
    validate_external_reference,
    validate_relation_endpoints,
)

# Прогресс — забота интерфейса: контекст не меняет контракты адаптеров и анализаторов.
progress: ContextVar[Callable[[str, int | None], None] | None] = ContextVar(
    "progress", default=None
)


def tick(stage: str, total: int | None = None) -> None:
    """Report one processed item of a counted stage, or the start of an uncounted one."""
    if (callback := progress.get()) is not None:
        callback(stage, total)


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
            elif isinstance(entity, SourceAnalysis):
                require(entity.source_file_id, SourceFile)
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
            elif isinstance(entity, OrmMapping):
                require(entity.symbol_id, Symbol)
                require(entity.owner_symbol_id, Symbol)
                if catalog[entity.owner_symbol_id].symbol_kind != "CLASS":
                    raise ValueError("ORM mapping owner must be a class")
                if (
                    entity.mapping_kind == "ENTITY"
                    and catalog[entity.symbol_id].symbol_kind != "CLASS"
                ):
                    raise ValueError("ORM entity mapping must use a class symbol")
                if entity.mapping_kind == "ATTRIBUTE" and catalog[
                    entity.symbol_id
                ].symbol_kind not in ("FIELD", "METHOD"):
                    raise ValueError("ORM attribute requires field/getter symbol")
                if entity.mapping_kind == "ATTRIBUTE":
                    symbol = catalog[entity.symbol_id]
                    owner = catalog[entity.owner_symbol_id]
                    if (
                        symbol.symbol_kind == "METHOD"
                        and symbol.owner_key != owner.logical_key
                    ):
                        raise ValueError("ORM getter must belong to its entity class")
                    if (
                        symbol.symbol_kind == "FIELD"
                        and catalog[symbol.scope_id].owner_symbol_id != owner.id
                    ):
                        raise ValueError("ORM field must belong to its entity class")
            elif isinstance(entity, OrmQuery):
                require(entity.owner_symbol_id, Symbol)
                if catalog[entity.owner_symbol_id].symbol_kind not in (
                    "CLASS",
                    "METHOD",
                    "CONSTRUCTOR",
                ):
                    raise ValueError("ORM query owner must be a type or callable")
            elif isinstance(entity, OrmOperation):
                require(entity.owner_symbol_id, Symbol)
                require(entity.call_operation_id, Operation)
                require(entity.query_id, OrmQuery)
                require(entity.context_id, DatabaseContext)
                operation = catalog[entity.call_operation_id]
                if (
                    catalog[entity.owner_symbol_id].symbol_kind
                    not in ("METHOD", "CONSTRUCTOR")
                    or operation.operation_kind != "CALL"
                    or operation.callee is None
                    or operation.callee.name != entity.api
                ):
                    raise ValueError("ORM invocation must use its callable/CALL API")
                scope = catalog.get(operation.scope_id)
                seen = set()
                owner = None
                while isinstance(scope, Scope) and scope.id not in seen:
                    seen.add(scope.id)
                    symbol = catalog.get(scope.owner_symbol_id)
                    if isinstance(symbol, Symbol) and symbol.symbol_kind in (
                        "METHOD",
                        "CONSTRUCTOR",
                    ):
                        owner = symbol.id
                        break
                    scope = catalog.get(scope.parent_scope_id)
                if owner != entity.owner_symbol_id:
                    raise ValueError(
                        "ORM CALL scope must belong to its invocation owner"
                    )
            elif isinstance(entity, (DatabaseContext, DatabaseObject)):
                require(entity.projection_file_id, SourceFile)
                if (
                    entity.source_range is not None
                    and entity.source_range.source_file_id != entity.projection_file_id
                ):
                    raise ValueError(
                        "database projection must belong to its source file"
                    )
            elif isinstance(entity, DatabaseAccess):
                require(entity.access_id, DataAccess)
                require(entity.context_id, DatabaseContext)
                require(entity.execution_id, SqlExecute)
            elif isinstance(entity, SqlPlaceholder):
                require(entity.statement_id, SqlStatement)
                statement = catalog[entity.statement_id]
                if (
                    statement.parse_status != "COMPLETE"
                    or statement.text[entity.text_start : entity.text_end]
                    != entity.token_text
                ):
                    raise ValueError(
                        "SQL placeholder must match a complete statement slice"
                    )
            elif isinstance(entity, SqlBinding):
                require(entity.execution_id, SqlExecute)
                require(entity.value_id, Value)
                require(entity.setter_operation_id, Operation)
                if entity.setter_operation_id is not None:
                    setter = catalog[entity.setter_operation_id]
                    if (
                        setter.operation_kind != "CALL"
                        or setter.callee is None
                        or setter.callee.name != entity.api
                    ):
                        raise ValueError("SQL binding setter must match a CALL API")
                    if entity.api.startswith("java.sql."):
                        if len(setter.input_value_ids) < 2:
                            raise ValueError(
                                "JDBC setter requires selector and value/type inputs"
                            )
                        selector = catalog[setter.input_value_ids[0]]
                        if entity.binding_kind == "POSITIONAL" and (
                            selector.value_kind != "LITERAL"
                            or type(selector.literal) is not int
                            or selector.literal != entity.position
                        ):
                            raise ValueError(
                                "binding selector must match JDBC setter input"
                            )
                        if entity.binding_kind == "NAMED" and (
                            selector.value_kind != "LITERAL"
                            or selector.literal != entity.parameter_name
                        ):
                            raise ValueError(
                                "binding selector must match JDBC setter input"
                            )
                        value = catalog[entity.value_id]
                        if entity.api.endswith(".setNull"):
                            if (
                                value.value_kind != "LITERAL"
                                or value.literal is not None
                            ):
                                raise ValueError(
                                    "setNull binding requires literal null"
                                )
                        elif setter.input_value_ids[1] != entity.value_id:
                            raise ValueError(
                                "binding value must match JDBC setter input"
                            )
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
        source_reports = [
            e.source_file_id for e in self.entities if isinstance(e, SourceAnalysis)
        ]
        if len(set(source_reports)) != len(source_reports):
            raise ValueError(
                "source file cannot have multiple adapter analysis reports"
            )
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
        parameter_keys: set[tuple[str, int]] = set()
        executable = {}
        for relation in self.entities:
            if (
                isinstance(relation, Relation)
                and relation.relation_kind == RelationKind.EXECUTES_STATEMENT
            ):
                refs = (
                    (relation.resolution.target,)
                    if relation.resolution.target
                    else relation.resolution.candidates
                )
                executable.setdefault(relation.source.id, set()).update(
                    ref.id for ref in refs
                )
        for entity in self.entities:
            if isinstance(entity, SqlPlaceholder):
                key = (entity.statement_id, entity.ordinal)
                if key in parameter_keys:
                    raise ValueError("duplicate SQL placeholder ordinal")
                parameter_keys.add(key)
            if (
                isinstance(entity, Relation)
                and entity.relation_kind == RelationKind.BINDS_PARAMETER
            ):
                binding = catalog[entity.source.id]
                targets = (
                    (entity.resolution.target,)
                    if entity.resolution.target
                    else entity.resolution.candidates
                )
                for ref in targets:
                    parameter = catalog[ref.id]
                    if parameter.statement_id not in executable.get(
                        binding.execution_id, set()
                    ):
                        raise ValueError(
                            "binding placeholder must belong to an execution statement"
                        )
                    if binding.binding_kind == "POSITIONAL" and (
                        parameter.parameter_kind != "POSITIONAL"
                        or binding.position != parameter.position
                    ):
                        raise ValueError(
                            "binding position must match the SQL placeholder"
                        )
                    if binding.binding_kind == "NAMED" and (
                        parameter.parameter_kind != "NAMED"
                        or binding.parameter_name != parameter.parameter_name
                    ):
                        raise ValueError("binding name must match the SQL placeholder")
                    if (
                        entity.resolution.status == "RESOLVED"
                        and binding.status != "BOUND"
                    ):
                        raise ValueError(
                            "incomplete SQL binding cannot assert definite parameter link"
                        )
        database_choices = {}
        for relation in self.entities:
            if (
                isinstance(relation, Relation)
                and relation.relation_kind == RelationKind.USES_DATABASE_CONTEXT
            ):
                refs = (
                    (relation.resolution.target,)
                    if relation.resolution.target
                    else relation.resolution.candidates
                )
                database_choices.setdefault(relation.source.id, set()).update(
                    ref.id for ref in refs
                )
        for entity in self.entities:
            if not isinstance(entity, DatabaseAccess) or entity.execution_id is None:
                continue
            access = catalog[entity.access_id]
            if access.statement_id not in executable.get(entity.execution_id, set()):
                raise ValueError(
                    "contextual database access must belong to an execution statement"
                )
            if (
                entity.context_id is not None
                and entity.context_id
                not in database_choices.get(entity.execution_id, set())
            ):
                raise ValueError(
                    "contextual database access must use an execution context"
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


# Сущностей на порцию: ограничивает строки, которые одновременно лежат в памяти.
_CHUNK = 20_000


def recheck[M: ContractModel](model: M) -> M:
    """Reparse JSON so model_construct/model_copy instances are checked, keeping no copy."""
    if type(model).model_validate_json(model.model_dump_json()) != model:
        raise ValueError("model changes under strict JSON revalidation")
    return model


def _record_chunks(
    snapshot_id: UUID, batch: UcmBatch
) -> Iterator[dict[str, list[dict]]]:
    """Recheck the whole batch, then yield normalized rows chunk by chunk."""
    starts = range(0, len(batch.entities), _CHUNK)
    for start in starts:
        for entity in batch.entities[start : start + _CHUNK]:
            recheck(entity)
        tick("Перепроверка сущностей", len(starts))
    tick("Проверка снимка")
    batch = UcmBatch(repository_id=batch.repository_id, entities=batch.entities)
    for start in starts:
        yield _rows(
            snapshot_id, batch.repository_id, batch.entities[start : start + _CHUNK]
        )
        tick("Запись в БД: загрузка", len(starts))


def _rows(
    snapshot_id: UUID, repository_id: UUID, entities: tuple[Entity, ...]
) -> dict[str, list[dict]]:
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

    for entity in entities:
        file_id, start_line, start_column, end_line, end_column = _range(
            entity.source_range
        )
        add(
            "ucm_entities",
            entity_id=entity.id,
            repository_id=repository_id,
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
        elif isinstance(entity, SourceAnalysis):
            add(
                "ucm_source_analyses",
                **base,
                source_file_id=entity.source_file_id,
                adapter_key=entity.adapter_key,
                adapter_version=entity.adapter_version,
                analysis_version=entity.analysis_version,
            )
            for capability in entity.capabilities:
                add(
                    "ucm_source_analysis_capabilities",
                    analysis_id=entity.id,
                    capability=capability.capability,
                    analyzer_version=capability.analyzer_version,
                    status=capability.status,
                )
                for ordinal, reason in enumerate(capability.reasons):
                    add(
                        "ucm_source_analysis_reasons",
                        analysis_id=entity.id,
                        capability=capability.capability,
                        ordinal=ordinal,
                        reason=reason,
                    )
            for ordinal, diagnostic in enumerate(entity.diagnostics):
                f, sl, sc, el, ec = _range(diagnostic.source_range)
                add(
                    "ucm_source_diagnostics",
                    analysis_id=entity.id,
                    ordinal=ordinal,
                    severity=diagnostic.severity,
                    code=diagnostic.code,
                    message=diagnostic.message,
                    source_file_id=f,
                    start_line=sl,
                    start_byte_column=sc,
                    end_line=el,
                    end_byte_column=ec,
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
        elif isinstance(entity, OrmMapping):
            add(
                "ucm_orm_mappings",
                **base,
                mapping_kind=entity.mapping_kind,
                entity_role=entity.entity_role,
                symbol_id=entity.symbol_id,
                owner_symbol_id=entity.owner_symbol_id,
                entity_name=entity.entity_name,
                attribute_name=entity.attribute_name,
                attribute_kind=entity.attribute_kind,
                access_mode=entity.access_mode,
                nullable=entity.nullable,
                insertable=entity.insertable,
                updatable=entity.updatable,
                status=entity.status,
            )
            for part in ("catalog_name", "schema_name", "table_name", "column_name"):
                identifier = getattr(entity, part)
                if identifier is not None:
                    add(
                        "ucm_orm_mapping_names",
                        mapping_id=entity.id,
                        part=part,
                        text=identifier.text,
                        quoted=identifier.quoted,
                        normalized=identifier.normalized,
                    )
            for ordinal, reason in enumerate(entity.reasons):
                add(
                    "ucm_orm_reasons",
                    owner_id=entity.id,
                    ordinal=ordinal,
                    reason=reason,
                )
        elif isinstance(entity, OrmQuery):
            add(
                "ucm_orm_queries",
                **base,
                owner_symbol_id=entity.owner_symbol_id,
                query_kind=entity.query_kind,
                query_name=entity.query_name,
                text=entity.text,
                status=entity.status,
            )
            for ordinal, reason in enumerate(entity.reasons):
                add(
                    "ucm_orm_reasons",
                    owner_id=entity.id,
                    ordinal=ordinal,
                    reason=reason,
                )
        elif isinstance(entity, OrmOperation):
            add(
                "ucm_orm_operations",
                **base,
                owner_symbol_id=entity.owner_symbol_id,
                call_operation_id=entity.call_operation_id,
                api=entity.api,
                operation_kind=entity.operation_kind,
                effect_kind=entity.effect_kind,
                query_id=entity.query_id,
                context_id=entity.context_id,
            )
        elif isinstance(entity, DatabaseObject):
            add(
                "ucm_database_objects",
                **base,
                projection_file_id=entity.projection_file_id,
                database_key=entity.database_key,
                version_key=entity.version_key,
                schema_fingerprint=entity.schema_fingerprint,
                object_key=entity.object_key,
                object_kind=entity.object_kind,
                catalog_name=entity.catalog_name,
                schema_name=entity.schema_name,
                table_name=entity.table_name,
                column_name=entity.column_name,
            )
        elif isinstance(entity, DatabaseContext):
            add(
                "ucm_database_contexts",
                **base,
                projection_file_id=entity.projection_file_id,
                connection_key=entity.connection_key,
                database_key=entity.database_key,
                version_key=entity.version_key,
                schema_fingerprint=entity.schema_fingerprint,
            )
            for position, name in enumerate(entity.search_path):
                add(
                    "ucm_database_search_paths",
                    context_id=entity.id,
                    position=position,
                    schema_name=name,
                )
        elif isinstance(entity, DatabaseAccess):
            add(
                "ucm_database_accesses",
                **base,
                access_id=entity.access_id,
                context_id=entity.context_id,
                execution_id=entity.execution_id,
            )
        elif isinstance(entity, SqlPlaceholder):
            add(
                "ucm_sql_placeholders",
                **base,
                statement_id=entity.statement_id,
                ordinal=entity.ordinal,
                parameter_kind=entity.parameter_kind,
                position=entity.position,
                parameter_name=entity.parameter_name,
                token_text=entity.token_text,
                text_start=entity.text_start,
                text_end=entity.text_end,
            )
        elif isinstance(entity, SqlBinding):
            add(
                "ucm_sql_bindings",
                **base,
                execution_id=entity.execution_id,
                value_id=entity.value_id,
                setter_operation_id=entity.setter_operation_id,
                api=entity.api,
                binding_kind=entity.binding_kind,
                position=entity.position,
                parameter_name=entity.parameter_name,
                status=entity.status,
            )
            for ordinal, reason in enumerate(entity.reasons):
                add(
                    "ucm_sql_binding_reasons",
                    binding_id=entity.id,
                    ordinal=ordinal,
                    reason=reason,
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
    async with conn.transaction():
        await _ingest_records(conn, snapshot_id, batch)
    return {entity.id: (snapshot_id, entity.id) for entity in batch.entities}


async def _ingest_records(
    conn: asyncpg.Connection,
    snapshot_id: UUID,
    batch: UcmBatch,
) -> None:
    """Validate the batch and write its records inside the caller's transaction."""
    repository_id = batch.repository_id
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
    stages: dict[str, tuple[str, str]] = {}
    chunks = _record_chunks(snapshot_id, batch)
    # Подготовка порции нагружает процессор; в потоке она не блокирует цикл событий.
    while (rows := await asyncio.to_thread(next, chunks, None)) is not None:
        for table, records in rows.items():
            columns = tuple(records[0])
            if table not in stages:
                stage = prefix + "_" + table.removeprefix("ucm_")
                stages[table] = (stage, ",".join(columns))
                await conn.execute(
                    f"CREATE TEMP TABLE {stage} (LIKE public.{table} INCLUDING DEFAULTS) ON COMMIT DROP"
                )
            await conn.copy_records_to_table(
                stages[table][0],
                schema_name="pg_temp",
                columns=columns,
                records=[tuple(row[column] for column in columns) for row in records],
            )
    # Envelope IDs first; deferred FKs allow cyclic subtype references in pass two.
    for table in ["ucm_entities", *(t for t in stages if t != "ucm_entities")]:
        if table not in stages:
            continue
        stage, columns = stages[table]
        await conn.execute(
            f"INSERT INTO public.{table} ({columns}) SELECT {columns} FROM pg_temp.{stage}"
        )
        tick("Запись в БД: перенос", len(stages))
    tick("Запись в БД: проверка связей")
    await conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
