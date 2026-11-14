"""Opt-in Java Value -> binding -> placeholder -> syntactic column lineage."""

import asyncio
import json
from collections import defaultdict
from pathlib import Path
from uuid import UUID

import asyncpg
from sqlglot.errors import SqlglotError

from code_crawler.incremental import (
    FileAnalysis,
    IncrementalResult,
    SourceInput,
    _capture,
    index_incremental,
)
from code_crawler.java_bindings import (
    BindingExecution,
    BindingFlow,
    CapturedBinding,
    CapturedValue,
)
from code_crawler.java_calls import _File
from code_crawler.java_semantic import JavaSemanticAnalyzer, _envelope, _relation
from code_crawler.java_sql import _recover
from code_crawler.sql_parameters import analyze_parameters
from code_crawler.sql_semantic import DIALECTS
from code_crawler.ucm import (
    Coverage,
    DataAccess,
    EntityRef,
    EntityType,
    Evidence,
    Operation,
    Relation,
    RelationKind,
    Resolution,
    SqlAccessDetail,
    SqlBinding,
    SqlConstruction,
    SqlExecute,
    SqlPlaceholder,
    SqlStatement,
    TypeRef,
    Value,
)


def _fingerprint(binding: CapturedBinding) -> str:
    value = binding.value
    return json.dumps(
        [
            binding.kind,
            binding.position,
            binding.name,
            value.node.start_byte,
            value.kind,
            value.literal,
            value.symbol_id,
            value.type_name,
            value.reasons,
            binding.setter.start_byte if binding.setter else None,
            binding.reasons,
        ],
        ensure_ascii=False,
        sort_keys=True,
    )


class JavaLineageAnalyzer(JavaSemanticAnalyzer):
    """Capture local binding snapshots and conservative SQL parameter associations."""

    def __init__(
        self, sources: tuple[SourceInput, ...], dialect: str = "postgres"
    ) -> None:
        super().__init__(sources, dialect)
        self.analysis_version = "java.sql.lineage/1:" + self.analysis_version
        self.lineage_coverage = Coverage(
            capability="sql.parameter.lineage",
            analyzer_version="1",
            status="PARTIAL",
            reasons=(
                "local scalar reaching definitions and supported JDBC/Spring overloads only",
                "batch queues, unknown containers, collection expansion and interprocedural value flow are not modeled",
            ),
        )

    def analysis(self, file: _File) -> FileAnalysis:
        base = super().analysis(file)
        entities = list(base.entities)
        repository = file.source.file.repository_id
        catalog = {e.id: e for e in entities}
        statements = defaultdict(list)
        for entity in entities:
            if isinstance(entity, SqlStatement):
                statements[entity.candidate_id].append(entity)
        placeholders: dict[str, SqlPlaceholder] = {}
        for candidate, ordered in sorted(statements.items()):
            if any(s.parse_status != "COMPLETE" for s in ordered):
                continue
            position = 0
            for statement in sorted(ordered, key=lambda s: s.statement_index):
                try:
                    parsed = analyze_parameters(statement.text, self.dialect, position)
                except (SqlglotError, ValueError, RecursionError):
                    continue
                position += sum(p.parameter_kind == "POSITIONAL" for p in parsed)
                for ordinal, parameter in enumerate(parsed, 1):
                    key = statement.logical_key + f":parameter:{ordinal}"
                    placeholder = SqlPlaceholder(
                        **_envelope(
                            repository,
                            EntityType.SQL_PLACEHOLDER,
                            key,
                            parameter.token_text,
                            statement.source_range,
                        ),
                        statement_id=statement.id,
                        ordinal=ordinal,
                        parameter_kind=parameter.parameter_kind,
                        position=parameter.position,
                        parameter_name=parameter.parameter_name,
                        token_text=parameter.token_text,
                        text_start=parameter.text_start,
                        text_end=parameter.text_end,
                    )
                    placeholders[placeholder.id] = placeholder
                    entities.append(placeholder)
                    evidence = Evidence(
                        source_range=statement.source_range,
                        analyzer="sql.lineage",
                        analyzer_version="1",
                        rule="ast-parameter",
                        description=f"True SQL AST placeholder at decoded statement chars [{parameter.text_start},{parameter.text_end})",
                    )
                    entities.append(
                        _relation(
                            repository,
                            key + ":owner",
                            RelationKind.HAS_SQL_PARAMETER,
                            EntityRef(
                                id=statement.id, entity_type=EntityType.SQL_STATEMENT
                            ),
                            Resolution(
                                status="RESOLVED",
                                target=EntityRef(
                                    id=placeholder.id,
                                    entity_type=EntityType.SQL_PLACEHOLDER,
                                ),
                            ),
                            evidence,
                            self.lineage_coverage,
                        )
                    )
                    matches = [
                        access
                        for access in base.entities
                        if isinstance(access, DataAccess)
                        and access.statement_id == statement.id
                        and any(
                            access.model_dump(include=set(SqlAccessDetail.model_fields))
                            == detail.model_dump()
                            for detail in parameter.columns
                        )
                    ]
                    refs = tuple(
                        EntityRef(id=a.id, entity_type=EntityType.DATA_ACCESS)
                        for a in sorted(matches, key=lambda a: a.id)
                    )
                    definite = (
                        len(matches) == 1 and matches[0].binding_status == "BOUND"
                    )
                    resolution = (
                        Resolution(status="RESOLVED", target=refs[0])
                        if definite
                        else Resolution(
                            status="PARTIAL" if refs else "UNRESOLVED",
                            candidates=refs,
                            reason=parameter.reason
                            or "ambiguous/unknown syntactic column association; database identity is unavailable",
                        )
                    )
                    entities.append(
                        _relation(
                            repository,
                            key + ":column",
                            RelationKind.PARAMETER_COLUMN,
                            EntityRef(
                                id=placeholder.id,
                                entity_type=EntityType.SQL_PLACEHOLDER,
                            ),
                            resolution,
                            evidence,
                            self.lineage_coverage,
                        )
                    )
        output: list[BindingExecution] = []
        for method in self.methods.values():
            if method.owner.file is not file:
                continue
            constants = file.result._extractor.parsed._constant_scopes.get(
                method.owner.symbol.qualified_name, {}
            )
            _recover(
                method.node,
                constants,
                True,
                BindingFlow(self, file, method.node, constants, output),
            )
        executions = {
            (e.source_range.start.line, e.source_range.start.byte_column): e
            for e in base.entities
            if isinstance(e, SqlExecute)
        }
        links = defaultdict(list)
        for entity in base.entities:
            if (
                isinstance(entity, Relation)
                and entity.relation_kind == RelationKind.EXECUTES_STATEMENT
            ):
                links[entity.source.id].append(entity)
        variant_construction = {
            variant.candidate_id: construction
            for construction in base.entities
            if isinstance(construction, SqlConstruction)
            for variant in construction.variants
        }
        grouped = defaultdict(list)
        for snapshot in output:
            point = snapshot.execution.site.node.start_point
            execution = executions.get((point.row + 1, point.column))
            if execution:
                grouped[execution.id].append(snapshot)
        for execution_id, snapshots in sorted(grouped.items()):
            execution = catalog[execution_id]
            branch_dependent = (
                len(
                    {
                        tuple(sorted(_fingerprint(b) for b in snapshot.bindings))
                        for snapshot in snapshots
                    }
                )
                > 1
            )
            generated = set()
            for snapshot in snapshots:
                eligible = []
                for link in links[execution_id]:
                    refs = (
                        (link.resolution.target,)
                        if link.resolution.target
                        else link.resolution.candidates
                    )
                    for ref in refs:
                        statement = catalog[ref.id]
                        construction = variant_construction[statement.candidate_id]
                        handle = snapshot.execution.handle
                        if handle and handle.value:
                            origin = file.result._extractor.range(handle.expression)
                            if origin != construction.source_range or not any(
                                v.candidate_id == statement.candidate_id
                                and v.text == handle.value.text.strip()
                                for v in construction.variants
                            ):
                                continue
                        eligible.extend(
                            p
                            for p in placeholders.values()
                            if p.statement_id == statement.id
                        )
                reasons = list(snapshot.reasons)
                if branch_dependent:
                    reasons.append("branch-dependent binding snapshot")
                for link in links[execution_id]:
                    if (
                        link.resolution.reason
                        and "unsupported" in link.resolution.reason
                    ):
                        reasons.append(link.resolution.reason)
                bindings = list(snapshot.bindings)
                selectors = {(b.kind, b.position, b.name) for b in bindings}
                for parameter in eligible:
                    selector = (
                        ("POSITIONAL", parameter.position, None)
                        if parameter.parameter_kind == "POSITIONAL"
                        else ("NAMED", None, parameter.parameter_name)
                        if parameter.parameter_kind == "NAMED"
                        and parameter.token_text.startswith(":")
                        else None
                    )
                    if selector is not None and selector not in selectors:
                        selectors.add(selector)
                        missing = CapturedValue(
                            snapshot.execution.site.node,
                            "UNKNOWN",
                            reasons=("no reaching Java binding value",),
                        )
                        bindings.append(
                            CapturedBinding(
                                *selector,
                                missing,
                                None,
                                execution.api,
                                (
                                    "binding state is unknown"
                                    if reasons
                                    else "no reaching setter/argument for placeholder",
                                ),
                            )
                        )
                for binding in bindings:
                    signature = (
                        _fingerprint(binding),
                        tuple(sorted(reasons)),
                        tuple(sorted(p.id for p in eligible)),
                    )
                    if signature in generated:
                        continue
                    generated.add(signature)
                    index = len(generated) - 1
                    key = execution.logical_key + f":binding:{index}"
                    value = self._value(file, binding.value, key + ":value", entities)
                    extra = list(
                        dict.fromkeys(
                            (*reasons, *binding.reasons, *binding.value.reasons)
                        )
                    )
                    missing_value = binding.value.reasons == (
                        "no reaching Java binding value",
                    )
                    status = (
                        ("UNKNOWN" if reasons else "MISSING")
                        if missing_value
                        else "BOUND"
                        if not extra
                        else "PARTIAL"
                    )
                    if binding.kind == "UNKNOWN":
                        status = "UNKNOWN"
                    setter_id = None
                    if binding.setter:
                        site = self.sites[
                            (
                                file.source.file.path,
                                binding.setter.child_by_field_name("name").start_byte,
                            )
                        ]
                        inputs = []
                        for argument_index, argument in enumerate(binding.arguments):
                            if argument_index == 1 and not binding.api.endswith(
                                ".setNull"
                            ):
                                inputs.append(value.id)
                            else:
                                inputs.append(
                                    self._value(
                                        file,
                                        argument,
                                        key + f":setter-arg:{argument_index}",
                                        entities,
                                    ).id
                                )
                        operation = Operation(
                            **_envelope(
                                repository,
                                EntityType.OPERATION,
                                key + ":setter",
                                binding.api,
                                file.result._extractor.range(binding.setter),
                            ),
                            operation_kind="CALL",
                            scope_id=site.occurrence.scope_id,
                            input_value_ids=tuple(inputs),
                            callee=TypeRef(name=binding.api),
                        )
                        entities.append(operation)
                        setter_id = operation.id
                    elif status == "BOUND":
                        setter_id = execution.operation_id
                    fact = SqlBinding(
                        **_envelope(
                            repository,
                            EntityType.SQL_BINDING,
                            key,
                            binding.api,
                            file.result._extractor.range(
                                binding.setter or snapshot.execution.site.node
                            ),
                        ),
                        execution_id=execution.id,
                        value_id=value.id,
                        setter_operation_id=setter_id,
                        api=binding.api,
                        binding_kind=binding.kind,
                        position=binding.position,
                        parameter_name=binding.name,
                        status=status,
                        reasons=tuple(extra),
                    )
                    entities.append(fact)
                    evidence = Evidence(
                        source_range=fact.source_range,
                        analyzer="java.sql.lineage",
                        analyzer_version="1",
                        rule="execution-binding-snapshot",
                        description="Reaching Java value and selector captured for this execution; later setters cannot mutate the snapshot",
                    )
                    for kind, source, target in (
                        (
                            RelationKind.HAS_SQL_BINDING,
                            EntityRef(
                                id=execution.id, entity_type=EntityType.SQL_EXECUTE
                            ),
                            EntityRef(id=fact.id, entity_type=EntityType.SQL_BINDING),
                        ),
                        (
                            RelationKind.VALUE_BINDS_SQL,
                            EntityRef(id=value.id, entity_type=EntityType.VALUE),
                            EntityRef(id=fact.id, entity_type=EntityType.SQL_BINDING),
                        ),
                    ):
                        entities.append(
                            _relation(
                                repository,
                                key + ":" + kind.value,
                                kind,
                                source,
                                Resolution(status="RESOLVED", target=target),
                                evidence,
                                self.lineage_coverage,
                            )
                        )
                    matched = [
                        p
                        for p in eligible
                        if (
                            binding.kind == "POSITIONAL"
                            and p.parameter_kind == "POSITIONAL"
                            and binding.position == p.position
                        )
                        or (
                            binding.kind == "NAMED"
                            and p.parameter_kind == "NAMED"
                            and p.token_text.startswith(":")
                            and binding.name == p.parameter_name
                            and ".namedparam." in binding.api
                        )
                    ]
                    if not matched:
                        resolutions = [
                            Resolution(
                                status="UNRESOLVED",
                                reason="no compatible SQL placeholder for this binding selector/origin",
                            )
                        ]
                    else:
                        resolutions = []
                        for parameter in matched:
                            ref = EntityRef(
                                id=parameter.id, entity_type=EntityType.SQL_PLACEHOLDER
                            )
                            definite = status == "BOUND" and all(
                                link.resolution.status == "RESOLVED"
                                for link in links[execution_id]
                            )
                            resolutions.append(
                                Resolution(status="RESOLVED", target=ref)
                                if definite
                                else Resolution(
                                    status="PARTIAL",
                                    candidates=(ref,),
                                    reason="; ".join(extra)
                                    or "SQL origin/statement is partial",
                                )
                            )
                    for relation_index, resolution in enumerate(resolutions):
                        entities.append(
                            _relation(
                                repository,
                                key + f":parameter:{relation_index}",
                                RelationKind.BINDS_PARAMETER,
                                EntityRef(
                                    id=fact.id, entity_type=EntityType.SQL_BINDING
                                ),
                                resolution,
                                evidence,
                                self.lineage_coverage,
                            )
                        )
        return FileAnalysis(
            path=base.path, entities=tuple(entities), dependencies=base.dependencies
        )

    def _value(
        self, file: _File, captured: CapturedValue, key: str, entities: list
    ) -> Value:
        value = Value(
            **_envelope(
                file.source.file.repository_id,
                EntityType.VALUE,
                key,
                captured.kind,
                file.result._extractor.range(captured.node),
            ),
            value_kind=captured.kind,
            literal=captured.literal,
            type_ref=TypeRef(name=captured.type_name) if captured.type_name else None,
            partial=captured.kind == "UNKNOWN",
        )
        entities.append(value)
        if captured.symbol_id:
            evidence = Evidence(
                source_range=value.source_range,
                analyzer="java.sql.lineage",
                analyzer_version="1",
                rule="local-value-origin",
                description="Scalar reaching definition or runtime Java symbol read at this source range",
            )
            entities.append(
                _relation(
                    value.repository_id,
                    key + ":symbol",
                    RelationKind.VALUE_OF,
                    EntityRef(id=value.id, entity_type=EntityType.VALUE),
                    Resolution(
                        status="RESOLVED",
                        target=EntityRef(
                            id=captured.symbol_id, entity_type=EntityType.SYMBOL
                        ),
                    ),
                    evidence,
                    self.lineage_coverage,
                )
            )
        return value


async def index_java_lineage(
    conn: asyncpg.Connection, repository_id: UUID, root: Path, dialect: str = "postgres"
) -> IncrementalResult:
    """Build parameter lineage in a BUILDING snapshot; caller validates/publishes."""
    if dialect not in DIALECTS:
        raise ValueError("unsupported SQL dialect profile")
    root = await asyncio.to_thread(root.resolve, strict=True)
    captured = await _capture(root, repository_id, {".java": "java"})
    analyzer = await asyncio.to_thread(
        JavaLineageAnalyzer,
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
