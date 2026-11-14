"""Java SQL discovery/construction; execution is deliberately not inferred."""

import asyncio
import copy
import json
from collections import defaultdict
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
from code_crawler.java_calls import JavaCallAnalyzer, _File
from code_crawler.java_symbols import _EXCLUDED, _parameter
from code_crawler.sql import looks_like_sql
from code_crawler.ucm import (
    Certainty,
    CodeEntity,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    Relation,
    RelationKind,
    Resolution,
    SourceRange,
    SqlConstruction,
    SqlFragment,
    SqlVariant,
    Symbol,
    logical_id,
)

_MAX_PATHS = 32


class _SqlFlow(java._Flow):
    def __init__(self, constants: dict, span: java.SourceSpan) -> None:
        super().__init__(constants, [])
        self.fallback = span
        self.frames: list[dict[str, java._Variable | None]] = []
        self.choices: dict[int, Node] = {}
        self.path_reasons: tuple[str, ...] = ()
        self.builder_names: frozenset[str] = frozenset()

    def clone(self) -> "_SqlFlow":
        result = copy.copy(self)
        result.variables, result.frames = copy.deepcopy((self.variables, self.frames))
        result.choices = dict(self.choices)
        result.queries = list(self.queries)
        result.reads = set()
        return result

    def push(self) -> None:
        self.frames.append({})

    def pop(self) -> None:
        for name, prior in self.frames.pop().items():
            value = self.variables[name]
            if value.dirty:
                self._emit(value.value, value.line, value.source_span)
            if prior is None:
                self.variables.pop(name)
            else:
                self.variables[name] = prior

    def _declare(self, declarator: Node, depth: int) -> None:
        name = java._text(declarator.child_by_field_name("name"))
        if self.frames and name not in self.frames[-1]:
            self.frames[-1][name] = self.variables.get(name)
        super()._declare(declarator, depth)
        initializer = declarator.child_by_field_name("value")
        if initializer is not None:
            self.variables[name].source_span = java._span(initializer)
            if (
                name in self.builder_names
                and initializer.type == "identifier"
                and java._text(initializer) in self.builder_names
            ):
                self.path_reasons = tuple(
                    dict.fromkeys(
                        (*self.path_reasons, "builder aliasing is not modeled")
                    )
                )

    def _visit(self, node: Node, depth: int) -> None:
        if (
            node.type in _EXCLUDED
            or node.type in java._TYPES
            or node.type in java._METHODS
        ):
            return
        if node.type == "object_creation_expression" and any(
            c.type == "class_body" for c in node.named_children
        ):
            return
        if node.type == "method_invocation":
            arguments = node.child_by_field_name("arguments")
            if arguments is not None and any(
                a.type == "identifier" and java._text(a) in self.builder_names
                for a in arguments.named_children
            ):
                self.path_reasons = tuple(
                    dict.fromkeys(
                        (*self.path_reasons, "builder may escape to an unknown call")
                    )
                )
        super()._visit(node, depth)

    def _invocation(self, node: Node, depth: int) -> None:
        name = java._text(node.child_by_field_name("name"))
        root = java._chain_root(node)
        variable = self.variables.get(java._text(root)) if root is not None else None
        if (
            root is not None
            and java._text(root) in self.builder_names
            and variable is not None
        ):
            pure = {
                "append",
                "toString",
                "length",
                "capacity",
                "charAt",
                "indexOf",
                "lastIndexOf",
                "ensureCapacity",
                "trimToSize",
            }
            arguments = node.child_by_field_name("arguments")
            reset = (
                name == "setLength"
                and arguments is not None
                and len(arguments.named_children) == 1
                and java._text(arguments.named_children[0]) == "0"
            )
            if name not in pure and not reset and variable.value is not None:
                value = variable.value
                variable.value = java._Value(
                    value.text,
                    True,
                    value.fragments,
                    tuple(
                        dict.fromkeys((*value.reasons, "unsupported builder mutation"))
                    ),
                )
                variable.dirty = True
                variable.source_span = java._span(node)
                return
        super()._invocation(node, depth)

    def evaluate(self, node: Node) -> java._Value | None:
        if node.type == "ternary_expression":
            chosen = self.choices.get(node.id)
            return self.evaluate(chosen) if chosen else None
        if node.type == "character_literal":
            text = java._literal(node)
            return java._Value(
                text,
                fragments=(java._Fragment(text, False, java._span(node)),),
                is_string=False,
            )
        value = super().evaluate(node)
        if (
            value is not None
            and node.type == "method_invocation"
            and java._text(node.child_by_field_name("name"))
            in ("toLowerCase", "toUpperCase", "stripIndent", "insert")
        ):
            value = java._Value(
                value.text,
                True,
                value.fragments,
                tuple(
                    dict.fromkeys((*value.reasons, "unsupported string transformation"))
                ),
            )
        return value

    def _emit(
        self,
        value: java._Value | None,
        line: int,
        source_span: java.SourceSpan | None = None,
    ) -> None:
        if value is None or not looks_like_sql(value.text):
            return
        fragments = java._trim_fragments(value)
        reasons = tuple(dict.fromkeys((*value.reasons, *self.path_reasons)))
        if value.partial and not reasons:
            reasons = ("partial recovery",)
        if any(f.dynamic for f in fragments) and not reasons:
            reasons = ("dynamic fragment",)
        query = java.Query(
            value.text.strip(),
            bool(reasons),
            line,
            source_span or self.fallback,
            fragments,
            reasons,
        )
        if query not in self.queries:
            self.queries.append(query)


def _limit(flows: list[_SqlFlow]) -> list[_SqlFlow]:
    if len(flows) > _MAX_PATHS:
        raise ValueError(
            "SQL construction path limit exceeded; variants were not silently dropped"
        )
    return flows


def _ternaries(node: Node) -> list[Node]:
    found = []
    pending = [node]
    while pending:
        current = pending.pop()
        if current.type in _EXCLUDED or current.type in java._TYPES:
            continue
        if current.type == "ternary_expression":
            found.append(current)
        pending.extend(reversed(current.named_children))
    return found


def _paths(node: Node | None, flows: list[_SqlFlow]) -> list[_SqlFlow]:
    if (
        node is None
        or node.type in _EXCLUDED
        or node.type in java._TYPES
        or node.type in java._METHODS
    ):
        return flows
    if node.type in ("block", "constructor_body"):
        for flow in flows:
            flow.push()
        for child in node.named_children:
            flows = _paths(child, flows)
        for flow in flows:
            flow.pop()
        return flows
    if node.type == "if_statement":
        result = []
        for flow in flows:
            condition = node.child_by_field_name("condition")
            if condition:
                flow._visit(condition, 0)
            result.extend(
                _paths(node.child_by_field_name("consequence"), [flow.clone()])
            )
            result.extend(
                _paths(node.child_by_field_name("alternative"), [flow.clone()])
            )
        return _limit(result)
    if node.type in ("for_statement", "while_statement", "do_statement"):
        result = []
        for flow in flows:
            zero = flow.clone()
            zero.path_reasons = tuple(
                dict.fromkeys((*zero.path_reasons, "loop repetition is bounded"))
            )
            one = zero.clone()
            result.append(zero)
            result.extend(_paths(node.child_by_field_name("body"), [one]))
        return _limit(result)
    if node.type in (
        "local_variable_declaration",
        *java._FIELDS,
        "assignment_expression",
        "method_invocation",
        "return_statement",
        "annotation",
        "marker_annotation",
    ):
        for ternary in _ternaries(node):
            expanded = []
            for flow in flows:
                if ternary.id in flow.choices:
                    expanded.append(flow)
                    continue
                for branch in ("consequence", "alternative"):
                    selected = ternary.child_by_field_name(branch)
                    if selected is not None:
                        variant = flow.clone()
                        variant.choices[ternary.id] = selected
                        expanded.append(variant)
            flows = _limit(expanded)
        for flow in flows:
            flow._visit(node, 0)
        return flows
    for child in node.named_children:
        flows = _paths(child, flows)
    return flows


def _recover(node: Node, constants: dict, method: bool) -> list[java.Query]:
    flow = _SqlFlow(constants, java._span(node))
    pending = [node]
    builders = set()
    while pending:
        current = pending.pop()
        if current != node and (
            current.type in _EXCLUDED
            or current.type in java._TYPES
            or current.type in java._METHODS
        ):
            continue
        type_node = current.child_by_field_name("type")
        if java._text(type_node) in java._BUILDERS:
            if current.type == "formal_parameter":
                builders.add(java._text(current.child_by_field_name("name")))
            for declaration in current.children_by_field_name("declarator"):
                builders.add(java._text(declaration.child_by_field_name("name")))
        pending.extend(current.named_children)
    flow.builder_names = frozenset(builders)
    queries = []
    if method:
        modifiers = next(
            (c for c in node.named_children if c.type == "modifiers"), None
        )
        if modifiers:
            flow._visit(modifiers, 0)
            queries.extend(flow.queries)
            flow.queries = []
        params = node.child_by_field_name("parameters")
        if params:
            for param in params.named_children:
                if param.type in ("formal_parameter", "spread_parameter"):
                    name, _ = _parameter(param)
                    if name:
                        flow.variables[java._text(name)] = java._Variable(
                            None, 0, False, java._line(name), java._span(name)
                        )
        flows = _paths(node.child_by_field_name("body"), [flow])
    else:
        flows = [flow]
        for member in java._members(node.child_by_field_name("body")):
            if member.type in java._FIELDS:
                flows = _paths(member, flows)
    # Literal discovery is independent of whether an enclosing expression looks like SQL.
    pending = [c for c in node.named_children if c.type == "modifiers"]
    if method:
        body = node.child_by_field_name("body")
        if body is not None:
            pending.append(body)
    else:
        pending.extend(
            c
            for c in java._members(node.child_by_field_name("body"))
            if c.type in java._FIELDS
        )
    literal_flow = _SqlFlow(constants, java._span(node))
    while pending:
        current = pending.pop()
        if (
            current.type in _EXCLUDED
            or current.type in java._TYPES
            or current.type in java._METHODS
        ):
            continue
        if current.type in (
            "annotation",
            "marker_annotation",
        ) and java._is_jpql_annotation(current):
            continue
        if current.type == "object_creation_expression" and any(
            c.type == "class_body" for c in current.named_children
        ):
            continue
        if (
            current.type == "method_invocation"
            and java._text(current.child_by_field_name("name")) in java._JPQL_CALLS
        ):
            continue
        if current.type == "string_literal":
            literal_flow._emit(
                literal_flow.evaluate(current), java._line(current), java._span(current)
            )
        pending.extend(reversed(current.named_children))
    queries.extend(literal_flow.queries)
    for state in flows:
        for variable in state.variables.values():
            if variable.dirty:
                state._emit(variable.value, variable.line, variable.source_span)
        queries.extend(state.queries)
    return queries


class JavaSqlAnalyzer(JavaCallAnalyzer):
    """Calls plus same-file scoped SQL construction; no execution sink inference."""

    def __init__(self, sources: tuple[SourceInput, ...]) -> None:
        super().__init__(sources)
        self.analysis_version = "java.sql/1:" + self.analysis_version
        self.sql_coverage = Coverage(
            capability="java.sql.construction",
            analyzer_version="1",
            status="PARTIAL",
            reasons=(
                "SQL discovery is not execution; sink detection is separate",
                "bounded paths, same-file constants and partial Java string semantics",
            ),
        )

    def analysis(self, file: _File) -> FileAnalysis:
        base = super().analysis(file)
        entities = list(base.entities)
        extractor = file.result._extractor
        owners = [
            e
            for e in file.result.analysis.entities
            if isinstance(e, Symbol)
            and e.symbol_kind in ("CLASS", "METHOD", "CONSTRUCTOR")
        ]
        for owner in owners:
            node = extractor.symbol_nodes[owner.id]
            class_info = (
                self.class_keys.get(owner.logical_key)
                if owner.symbol_kind == "CLASS"
                else self.methods[owner.id].owner
            )
            constants = extractor.parsed._constant_scopes.get(
                class_info.symbol.qualified_name, {}
            )
            recovered = _recover(node, constants, owner.symbol_kind != "CLASS")
            grouped = defaultdict(list)
            for query in recovered:
                if query.source_span is not None:
                    grouped[
                        query.source_span.start_byte, query.source_span.end_byte
                    ].append(query)
            for (start, end), queries in sorted(grouped.items()):
                key = json.dumps(
                    ["java.sql", owner.logical_key, file.source.file.path, start, end],
                    separators=(",", ":"),
                )
                construction_id = logical_id(
                    owner.repository_id, EntityType.SQL_CONSTRUCTION, key
                )
                location = SourceRange(
                    source_file_id=file.source.file.id,
                    start=queries[0].source_span.start,
                    end=queries[0].source_span.end,
                )
                unique = {
                    json.dumps(
                        [
                            q.text,
                            q.partial,
                            [
                                (
                                    f.text,
                                    f.dynamic,
                                    f.source_span.start_byte if f.source_span else None,
                                    f.source_span.end_byte if f.source_span else None,
                                )
                                for f in q.fragments
                            ],
                            q.partial_reasons,
                        ],
                        ensure_ascii=False,
                    ): q
                    for q in queries
                }
                variants = []
                for index, (_, query) in enumerate(sorted(unique.items())):
                    candidate_key = key + f":candidate:{index}"
                    candidate = CodeEntity(
                        repository_id=owner.repository_id,
                        logical_key=candidate_key,
                        id=logical_id(
                            owner.repository_id, EntityType.SQL_CANDIDATE, candidate_key
                        ),
                        entity_type=EntityType.SQL_CANDIDATE,
                        name=" ".join(query.text.split())[:120],
                        source_range=location,
                    )
                    entities.append(candidate)
                    fragments = tuple(
                        SqlFragment(
                            kind="DYNAMIC" if f.dynamic else "STATIC",
                            text=f.text,
                            source_range=SourceRange(
                                source_file_id=file.source.file.id,
                                start=f.source_span.start,
                                end=f.source_span.end,
                            )
                            if f.source_span
                            else None,
                        )
                        for f in query.fragments
                    )
                    variants.append(
                        SqlVariant(
                            candidate_id=candidate.id,
                            text=query.text,
                            partial=query.partial,
                            partial_reasons=query.partial_reasons,
                            fragments=fragments,
                        )
                    )
                construction = SqlConstruction(
                    repository_id=owner.repository_id,
                    logical_key=key,
                    id=construction_id,
                    name="SQL construction",
                    owner_symbol_id=owner.id,
                    source_range=location,
                    variants=tuple(variants),
                )
                entities.append(construction)
                evidence = Evidence(
                    source_range=location,
                    analyzer="java.sql",
                    analyzer_version="1",
                    rule="static-string-recovery",
                    description="Possible SQL text construction, not proof of execution",
                )
                relations = [
                    (
                        RelationKind.CONSTRUCTS_SQL,
                        EntityRef(id=owner.id, entity_type=EntityType.SYMBOL),
                        EntityRef(
                            id=construction.id, entity_type=EntityType.SQL_CONSTRUCTION
                        ),
                    )
                ]
                relations.extend(
                    (
                        RelationKind.HAS_SQL_CANDIDATE,
                        EntityRef(
                            id=construction.id, entity_type=EntityType.SQL_CONSTRUCTION
                        ),
                        EntityRef(
                            id=v.candidate_id, entity_type=EntityType.SQL_CANDIDATE
                        ),
                    )
                    for v in variants
                )
                for index, (kind, source, target) in enumerate(relations):
                    relation_key = key + f":relation:{index}"
                    entities.append(
                        Relation(
                            repository_id=owner.repository_id,
                            logical_key=relation_key,
                            id=logical_id(
                                owner.repository_id, EntityType.RELATION, relation_key
                            ),
                            name=kind.value,
                            relation_kind=kind,
                            source=source,
                            resolution=Resolution(status="RESOLVED", target=target),
                            certainty=Certainty.INFERRED,
                            evidence=(evidence,),
                            coverage=self.sql_coverage,
                        )
                    )
        return FileAnalysis(
            path=base.path, entities=tuple(entities), dependencies=base.dependencies
        )


async def index_java_sql(
    conn: asyncpg.Connection, repository_id: UUID, root: Path
) -> IncrementalResult:
    """Build a SQL construction snapshot; caller explicitly validates and publishes."""
    root = await asyncio.to_thread(root.resolve, strict=True)
    captured = await _capture(root, repository_id, {".java": "java"})
    analyzer = await asyncio.to_thread(
        JavaSqlAnalyzer, tuple(s for s in captured.sources if s.file.language == "java")
    )
    return await index_incremental(
        conn,
        repository_id,
        root,
        analyzer,
        languages={".java": "java"},
        analysis_version=analyzer.analysis_version,
    )
