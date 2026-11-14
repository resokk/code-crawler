"""Typed Java JDBC/Spring execution sites, independent of SQL discovery."""

import asyncio
import copy
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

import asyncpg
from tree_sitter import Node

from code_crawler import java
from code_crawler.incremental import (
    FileAnalysis,
    IncrementalResult,
    SourceInput,
    _capture,
    index_incremental,
)
from code_crawler.java_calls import _File, _Site
from code_crawler.java_sql import JavaSqlAnalyzer, _recover, _SqlFlow
from code_crawler.ucm import (
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    Operation,
    Relation,
    RelationKind,
    Resolution,
    SqlConstruction,
    SqlExecute,
    TypeRef,
    Value,
    logical_id,
)

_STATEMENTS = {
    "java.sql.Statement",
    "java.sql.PreparedStatement",
    "java.sql.CallableStatement",
}
_PREPARED = _STATEMENTS - {"java.sql.Statement"}
_EXECUTE = {"execute", "executeQuery", "executeUpdate", "executeLargeUpdate"}
_SPRING = {
    "org.springframework.jdbc.core.JdbcTemplate",
    "org.springframework.jdbc.core.JdbcOperations",
    "org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate",
    "org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations",
}
_SPRING_METHODS = {
    "query",
    "queryForObject",
    "queryForList",
    "queryForMap",
    "queryForRowSet",
    "update",
    "execute",
    "batchUpdate",
}


@dataclass(frozen=True)
class _Handle:
    origin: int
    value: java._Value | None
    expression: Node
    receiver_type: str = "java.sql.PreparedStatement"
    connection_symbol_id: str | None = None


@dataclass(frozen=True)
class _Execution:
    site: _Site
    api: str
    sql_index: int | None
    handle: _Handle | None
    reason: str | None
    reasons: tuple[str, ...]
    arguments: tuple[java._Value | None, ...]


class _ExecutionFlow(_SqlFlow):
    def __init__(
        self,
        analyzer: "JavaExecutionAnalyzer",
        file: _File,
        node: Node,
        constants: dict,
        events: list[_Execution],
    ) -> None:
        super().__init__(constants, java._span(node))
        self.analyzer = analyzer
        self.file = file
        self.events = events
        self.handles: dict[str, _Handle] = {}
        self.created: dict[int, _Handle] = {}
        self.visited: set[int] = set()
        self.scopes = {n.id: scope for n, scope in file.result._extractor.nodes}

    def clone(self) -> "_ExecutionFlow":
        result = super().clone()
        result.handles = dict(self.handles)
        result.created = dict(self.created)
        result.visited = set(self.visited)
        return result

    def binding(self, node: Node | None) -> str | None:
        if node is None or node.type != "identifier":
            return None
        extractor = self.file.result._extractor
        declared = extractor.declarations.get(node.id)
        if declared:
            return (
                declared[0].id if declared[0].symbol_kind == "LOCAL_VARIABLE" else None
            )
        scope = self.scopes.get(node.id)
        if scope is None:
            return None
        found = extractor.lookup(
            java._text(node), scope, node.start_byte, {"LOCAL_VARIABLE", "PARAMETER"}
        )
        return found[0].id if len(found) == 1 else None

    def handle(self, node: Node | None) -> _Handle | None:
        if node is None:
            return None
        if node.type == "parenthesized_expression":
            return self.handle(node.named_children[0])
        if node.type == "method_invocation":
            return self.created.get(node.id)
        return self.handles.get(self.binding(node))

    def _declare(self, declarator: Node, depth: int) -> None:
        super()._declare(declarator, depth)
        key = self.binding(declarator.child_by_field_name("name"))
        if key:
            handle = self.handle(declarator.child_by_field_name("value"))
            if handle:
                self.handles[key] = handle
            else:
                self.handles.pop(key, None)

    def _assign(self, node: Node, depth: int) -> bool:
        result = super()._assign(node, depth)
        key = self.binding(node.child_by_field_name("left"))
        if key:
            handle = (
                self.handle(node.child_by_field_name("right"))
                if java._text(node.child_by_field_name("operator")) == "="
                else None
            )
            if handle:
                self.handles[key] = handle
            else:
                self.handles.pop(key, None)
        return result

    def invalidate(self, handle: _Handle | None) -> None:
        if handle:
            self.handles = {
                key: h for key, h in self.handles.items() if h.origin != handle.origin
            }
            self.created = {
                key: h for key, h in self.created.items() if h.origin != handle.origin
            }

    def escape(self, node: Node | None) -> None:
        pending = [node] if node is not None else []
        while pending:
            current = pending.pop()
            self.invalidate(self.handle(current))
            pending.extend(current.named_children)

    def preview(self, node: Node) -> java._Value | None:
        # Classification must not append to a builder a second time.
        return self.clone().evaluate(node)

    def is_string(self, node: Node, site: _Site) -> bool:
        descriptor = self.analyzer.argument_type(node, site)
        if descriptor is not None:
            return descriptor == "java.lang.String"
        value = self.preview(node)
        return value is not None and value.is_string

    def _visit(self, node: Node, depth: int) -> None:
        if (
            node.type == "assignment_expression"
            and self.binding(node.child_by_field_name("left")) is None
        ):
            self.escape(node.child_by_field_name("right"))
        super()._visit(node, depth)

    def _invocation(self, node: Node, depth: int) -> None:
        if node.id in self.visited:
            return
        self.visited.add(node.id)
        receiver = node.child_by_field_name("object")
        if (
            receiver is not None
            and receiver.type == "method_invocation"
            and self.preview(node) is None
        ):
            self._visit(receiver, depth)
        name_node = node.child_by_field_name("name")
        site = self.analyzer.sites.get(
            (self.file.source.file.path, name_node.start_byte)
        )
        args_node = node.child_by_field_name("arguments")
        args = tuple(args_node.named_children) if args_node else ()
        name = java._text(name_node)
        descriptor, is_class = self.analyzer.receiver(site) if site else (None, False)
        handle = self.handle(receiver)
        # External JDBC return types are intentionally absent from the Java call catalog.
        if descriptor is None and handle is not None:
            descriptor = handle.receiver_type
        trusted = not is_class and descriptor not in self.analyzer.classes
        if (
            trusted
            and descriptor == "java.sql.Connection"
            and name in ("prepareStatement", "prepareCall")
            and args
        ) and (self.is_string(args[0], site) or args[0].type == "string_literal"):
            self.created[node.id] = _Handle(
                node.start_byte,
                copy.deepcopy(self.preview(args[0])),
                args[0],
                "java.sql.CallableStatement"
                if name == "prepareCall"
                else "java.sql.PreparedStatement",
                self.analyzer.data_symbol(receiver, site).id
                if receiver is not None
                and self.analyzer.data_symbol(receiver, site) is not None
                else None,
            )
        if (
            trusted
            and descriptor == "java.sql.Connection"
            and name == "createStatement"
            and len(args) in (0, 2, 3)
        ):
            self.created[node.id] = _Handle(
                node.start_byte,
                None,
                node,
                "java.sql.Statement",
                self.analyzer.data_symbol(receiver, site).id
                if receiver is not None
                and self.analyzer.data_symbol(receiver, site) is not None
                else None,
            )
        sql_index = None
        recognized = False
        reason = None
        sql_handle = None
        if trusted and descriptor in _STATEMENTS:
            if name in _EXECUTE:
                if (
                    descriptor == "java.sql.Statement"
                    and args
                    and len(args) <= (1 if name == "executeQuery" else 2)
                ):
                    recognized = self.is_string(args[0], site)
                    sql_index = 0 if recognized else None
                elif descriptor in _PREPARED and not args:
                    recognized = True
                    sql_handle = handle
                    if handle is None:
                        reason = "prepared SQL origin is unknown, escaped, closed or outside this callable"
            elif name in ("executeBatch", "executeLargeBatch") and not args:
                recognized = True
                reason = "batch queue semantics are not modeled"
        elif (
            trusted
            and descriptor in _SPRING
            and name in _SPRING_METHODS
            and args
            and self.is_string(args[0], site)
        ):
            minimum = 2 if name in ("query", "queryForObject") else 1
            if ".namedparam." in descriptor:
                minimum = 3 if name == "queryForObject" else 2
            recognized = len(args) >= minimum
            sql_index = 0 if recognized else None
            if name == "batchUpdate":
                reason = "batch queue semantics are not modeled"
        if recognized:
            if sql_index is not None:
                sql_handle = _Handle(
                    node.start_byte,
                    copy.deepcopy(self.preview(args[sql_index])),
                    args[sql_index],
                    connection_symbol_id=handle.connection_symbol_id
                    if handle
                    else self.analyzer.data_symbol(receiver, site).id
                    if receiver is not None
                    and self.analyzer.data_symbol(receiver, site) is not None
                    else None,
                )
            self.events.append(
                _Execution(
                    site,
                    descriptor + "." + name,
                    sql_index,
                    sql_handle,
                    reason,
                    self.path_reasons,
                    tuple(copy.deepcopy(self.preview(arg)) for arg in args),
                )
            )
        if name == "close" and not args:
            self.invalidate(handle)
        # A passed handle may be closed/rebound or mutated by an unknown callee.
        for arg in args:
            self.escape(arg)
        super()._invocation(node, depth)


class JavaExecutionAnalyzer(JavaSqlAnalyzer):
    """Add statically recognized JDBC/Spring invocation sites to SQL construction."""

    def __init__(self, sources: tuple[SourceInput, ...]) -> None:
        super().__init__(sources)
        self.analysis_version = "java.sql.execution/1:" + self.analysis_version
        self.execution_coverage = Coverage(
            capability="java.sql.execution",
            analyzer_version="1",
            status="PARTIAL",
            reasons=(
                "exact declared JDBC/Spring types; local prepared origins only",
                "runtime reachability, batch queues, bindings and data effects are not analyzed",
            ),
        )

    def analysis(self, file: _File) -> FileAnalysis:
        base = super().analysis(file)
        entities = list(base.entities)
        events: list[_Execution] = []
        for method in self.methods.values():
            if method.owner.file is not file:
                continue
            constants = file.result._extractor.parsed._constant_scopes.get(
                method.owner.symbol.qualified_name, {}
            )
            local_events: list[_Execution] = []
            _recover(
                method.node,
                constants,
                True,
                _ExecutionFlow(self, file, method.node, constants, local_events),
            )
            pending = list(method.node.named_children)
            unsupported = False
            while pending:
                current = pending.pop()
                if current.type in (*java._TYPES, *java._METHODS, "lambda_expression"):
                    continue
                if current.type in (
                    "switch_expression",
                    "switch_statement",
                    "enhanced_for_statement",
                    "catch_clause",
                    "finally_clause",
                ):
                    unsupported = True
                pending.extend(current.named_children)
            for observed in local_events:
                if unsupported and (
                    observed.sql_index is None
                    or observed.site.node.child_by_field_name("arguments")
                    .named_children[observed.sql_index]
                    .type
                    != "string_literal"
                ):
                    observed = replace(
                        observed,
                        reason="SQL origin through switch/catch/finally/enhanced-loop is unsupported",
                    )
                events.append(observed)
        grouped = defaultdict(list)
        for event in events:
            grouped[event.site.node.start_byte].append(event)
        constructions = [e for e in base.entities if isinstance(e, SqlConstruction)]
        for start, observations in sorted(grouped.items()):
            event = observations[0]
            site = event.site
            location = file.result._extractor.range(site.node)
            key = site.occurrence.logical_key + ":sql-execute"

            def envelope(
                kind: EntityType,
                suffix: str = "",
                *,
                key: str = key,
                site: _Site = site,
                event: _Execution = event,
                location=location,
            ) -> dict:
                logical_key = key + suffix
                return {
                    "repository_id": site.occurrence.repository_id,
                    "logical_key": logical_key,
                    "id": logical_id(site.occurrence.repository_id, kind, logical_key),
                    "name": event.api,
                    "source_range": location,
                }

            values = []
            for index in range(len(event.arguments)):
                observed = [o.arguments[index] for o in observations]
                literal = observed[0]
                complete = (
                    literal is not None
                    and literal.is_string
                    and not literal.partial
                    and all(v == literal for v in observed)
                )
                argument = site.node.child_by_field_name("arguments").named_children[
                    index
                ]
                value_envelope = envelope(EntityType.VALUE, f":arg:{index}")
                value_envelope.update(
                    name=java._text(argument),
                    source_range=file.result._extractor.range(argument),
                )
                value = Value(
                    **value_envelope,
                    value_kind="LITERAL" if complete else "UNKNOWN",
                    literal=literal.text if complete else None,
                    partial=not complete,
                )
                entities.append(value)
                values.append(value.id)
            operation = Operation(
                **envelope(EntityType.OPERATION, ":call"),
                operation_kind="CALL",
                scope_id=site.occurrence.scope_id,
                input_value_ids=tuple(values),
                callee=TypeRef(name=event.api),
            )
            execution = SqlExecute(
                **envelope(EntityType.SQL_EXECUTE),
                owner_symbol_id=site.caller.symbol.id,
                operation_id=operation.id,
                api=event.api,
                sql_argument_index=event.sql_index,
            )
            entities.extend((operation, execution))
            evidence = [
                Evidence(
                    source_range=location,
                    analyzer="java.sql.execution",
                    analyzer_version="1",
                    rule="typed-execution-sink",
                    description="Statically recognized API invocation; runtime execution and effects are not proven",
                )
            ]
            targets = {}
            reasons = []
            for observation in observations:
                reasons.extend(observation.reasons)
                if observation.reason:
                    reasons.append(observation.reason)
                    continue
                h = observation.handle
                if h is None:
                    reasons.append("SQL argument cannot be recovered")
                    continue
                origin = file.result._extractor.range(h.expression)
                if origin != location and all(
                    e.source_range != origin for e in evidence
                ):
                    evidence.append(
                        Evidence(
                            source_range=origin,
                            analyzer="java.sql.execution",
                            analyzer_version="1",
                            rule="sql-origin",
                            description="SQL argument captured at this construction/preparation site",
                        )
                    )
                if h.value is None:
                    reasons.append("SQL argument cannot be recovered")
                    continue
                matching = [
                    c
                    for c in constructions
                    if c.owner_symbol_id == site.caller.symbol.id
                    and c.source_range == origin
                    and any(v.text == h.value.text.strip() for v in c.variants)
                ]
                if not matching:
                    reasons.append(
                        "no matching SQL construction at the argument origin"
                    )
                for construction in matching:
                    targets[construction.id] = EntityRef(
                        id=construction.id, entity_type=EntityType.SQL_CONSTRUCTION
                    )
                    if any(v.partial for v in construction.variants):
                        reasons.append("SQL construction is partial")
            refs = tuple(targets[k] for k in sorted(targets))
            if len(refs) == 1 and not reasons:
                resolution = Resolution(status="RESOLVED", target=refs[0])
            else:
                resolution = Resolution(
                    status="PARTIAL" if refs else "UNRESOLVED",
                    candidates=refs,
                    reason="; ".join(dict.fromkeys(reasons))
                    or "multiple possible SQL origins",
                )
            for kind, source, resolved in (
                (
                    RelationKind.EXECUTES_SQL,
                    EntityRef(id=site.caller.symbol.id, entity_type=EntityType.SYMBOL),
                    Resolution(
                        status="RESOLVED",
                        target=EntityRef(
                            id=execution.id, entity_type=EntityType.SQL_EXECUTE
                        ),
                    ),
                ),
                (
                    RelationKind.USES_SQL_CONSTRUCTION,
                    EntityRef(id=execution.id, entity_type=EntityType.SQL_EXECUTE),
                    resolution,
                ),
            ):
                entities.append(
                    Relation(
                        **envelope(EntityType.RELATION, ":" + kind.value),
                        relation_kind=kind,
                        source=source,
                        resolution=resolved,
                        certainty=Certainty.INFERRED
                        if resolved.status == "RESOLVED"
                        else Certainty.UNKNOWN,
                        evidence=tuple(evidence),
                        coverage=self.execution_coverage,
                    )
                )
        return FileAnalysis(
            path=base.path, entities=tuple(entities), dependencies=base.dependencies
        )


async def index_java_execution(
    conn: asyncpg.Connection, repository_id: UUID, root: Path
) -> IncrementalResult:
    """Build execution facts in a BUILDING snapshot; validation/publication are explicit."""
    root = await asyncio.to_thread(root.resolve, strict=True)
    captured = await _capture(root, repository_id, {".java": "java"})
    analyzer = await asyncio.to_thread(
        JavaExecutionAnalyzer,
        tuple(s for s in captured.sources if s.file.language == "java"),
    )
    return await index_incremental(
        conn,
        repository_id,
        root,
        analyzer,
        languages={".java": "java"},
        analysis_version=analyzer.analysis_version,
    )
