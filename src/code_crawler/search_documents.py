"""Search documents projected from UCM facts only: nothing is inferred while writing them."""

import hashlib
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from typing import Literal

from pydantic import Field

from code_crawler.data_security import DEFAULT_POLICY, SecretPolicy
from code_crawler.ucm import (
    ContractModel,
    DataAccess,
    DatabaseObject,
    Entity,
    EntityId,
    OrmMapping,
    OrmQuery,
    Relation,
    RelationKind,
    SourceFile,
    SqlExecute,
    SqlStatement,
    Symbol,
)

_VERBS = {
    "READ": "reads",
    "INSERT": "inserts into",
    "UPDATE": "updates",
    "DELETE": "deletes from",
    "MERGE": "merges into",
    "DDL": "alters",
}


class SearchDocument(ContractModel):
    id: str
    kind: Literal[
        "SYMBOL",
        "SQL_STATEMENT",
        "DATABASE_OBJECT",
        "CALL_SUMMARY",
        "ORM_MAPPING",
        "ORM_QUERY",
    ]
    entity_id: EntityId
    title: str
    text: str
    language: str | None = None
    path: str | None = None
    # Меняется только вместе с текстом: ключ для кэша эмбеддингов и пересчёта.
    content_sha256: str
    redaction: dict = Field(default_factory=dict)


def _document(
    kind: str, entity: Entity, title: str, lines: list[str], file: SourceFile | None
) -> SearchDocument:
    text = "\n".join(lines)
    return SearchDocument(
        id="doc:" + hashlib.sha256(f"{kind}\0{entity.id}".encode()).hexdigest(),
        kind=kind,
        entity_id=entity.id,
        title=title,
        text=text,
        language=file.language if file else None,
        path=file.path if file else None,
        content_sha256=hashlib.sha256(f"{title}\n{text}".encode()).hexdigest(),
    )


def _label(symbol: Symbol) -> str:
    if symbol.signature is None:
        return symbol.qualified_name
    types = ", ".join(t.name for t in symbol.signature.parameter_types)
    return f"{symbol.qualified_name}({types})"


def project(
    entities: Iterable[Entity], *, security_policy: SecretPolicy = DEFAULT_POLICY
) -> Iterator[SearchDocument]:
    """Yield sanitized derivative facts; original UCM entities remain unchanged."""
    for document in _project_raw(entities):
        payload = {
            "title": document.title,
            "text": document.text,
            "language": document.language,
            "path": document.path,
        }
        # A truncated SQL title could disclose part of a credential without context.
        if document.kind == "SQL_STATEMENT":
            payload["title"] = document.text.splitlines()[0]
        safe, report = security_policy.clean(payload)
        if safe is None:
            continue
        yield document.model_copy(
            update={
                **safe,
                "redaction": report,
                "content_sha256": hashlib.sha256(
                    f"{safe['title']}\n{safe['text']}".encode()
                ).hexdigest(),
            }
        )


def _project_raw(entities: Iterable[Entity]) -> Iterator[SearchDocument]:
    """Yield deterministic documents for symbols, SQL, ORM, DB objects and calls.

    Parameters and local variables get no document of their own. Every relation
    mentioned carries its certainty; unresolved facts are counted, never guessed.
    """
    catalog = {entity.id: entity for entity in entities}
    files = {e.id: e for e in catalog.values() if isinstance(e, SourceFile)}

    def file_of(entity: Entity) -> SourceFile | None:
        location = entity.source_range
        return files.get(location.source_file_id) if location else None

    def where(entity: Entity) -> list[str]:
        file = file_of(entity)
        if file is None:
            return []
        location = entity.source_range
        return [
            f"language: {file.language}",
            f"file: {file.path}:{location.start.line}-{location.end.line}",
        ]

    accesses: dict[str, list[DataAccess]] = defaultdict(list)
    executions: dict[str, list[Relation]] = defaultdict(list)
    calls_out: dict[str, list[Relation]] = defaultdict(list)
    calls_in: dict[str, list[Relation]] = defaultdict(list)
    for entity in catalog.values():
        if isinstance(entity, DataAccess):
            accesses[entity.statement_id].append(entity)
        elif isinstance(entity, Relation):
            target = entity.resolution.target
            if entity.relation_kind == RelationKind.EXECUTES_STATEMENT and target:
                executions[target.id].append(entity)
            elif entity.relation_kind == RelationKind.CALLS:
                calls_out[entity.source.id].append(entity)
                if target:
                    calls_in[target.id].append(entity)

    for entity in sorted(catalog.values(), key=lambda e: e.id):
        if isinstance(entity, Symbol) and entity.symbol_kind not in (
            "PARAMETER",
            "LOCAL_VARIABLE",
        ):
            lines = [f"{entity.symbol_kind} {_label(entity)}"]
            if entity.signature is not None and entity.signature.return_type:
                lines.append(f"returns: {entity.signature.return_type.name}")
            if entity.type_ref is not None:
                lines.append(f"type: {entity.type_ref.name}")
            yield _document(
                "SYMBOL", entity, _label(entity), lines + where(entity), file_of(entity)
            )
            outgoing, incoming = calls_out[entity.id], calls_in[entity.id]
            if outgoing or incoming:
                yield _document(
                    "CALL_SUMMARY",
                    entity,
                    f"Calls of {_label(entity)}",
                    _calls(catalog, outgoing, incoming),
                    file_of(entity),
                )
        elif isinstance(entity, SqlStatement):
            lines = [
                (
                    f"{entity.operation} statement, dialect {entity.dialect}, "
                    f"parse {entity.parse_status}"
                ),
                entity.text,
                *(f"parse note: {reason}" for reason in entity.reasons),
            ]
            lines += sorted({_access(access) for access in accesses[entity.id]})
            executed = sorted(
                f"executed by {_label(catalog[sink.owner_symbol_id])} via {sink.api} "
                f"[{relation.certainty}]"
                for relation in executions[entity.id]
                if isinstance(sink := catalog.get(relation.source.id), SqlExecute)
            )
            lines += executed or ["no execution fact recorded"]
            yield _document(
                "SQL_STATEMENT",
                entity,
                f"{entity.operation} {' '.join(entity.text.split())[:80]}",
                lines + where(entity),
                file_of(entity),
            )
        elif isinstance(entity, OrmQuery):
            yield _document(
                "ORM_QUERY",
                entity,
                entity.query_name or entity.name,
                [
                    f"{entity.query_kind} query, status {entity.status}",
                    *([entity.text] if entity.text else []),
                    *(f"query note: {reason}" for reason in sorted(entity.reasons)),
                ]
                + where(entity),
                file_of(entity),
            )
        elif isinstance(entity, OrmMapping):
            names = [
                f"{part}: {value.normalized}"
                for part in ("catalog_name", "schema_name", "table_name", "column_name")
                if (value := getattr(entity, part)) is not None
            ]
            yield _document(
                "ORM_MAPPING",
                entity,
                entity.entity_name,
                [
                    f"{entity.mapping_kind} mapping, status {entity.status}",
                    f"entity: {entity.entity_name}",
                    *names,
                    *(f"mapping note: {reason}" for reason in sorted(entity.reasons)),
                ]
                + where(entity),
                file_of(entity),
            )
        elif isinstance(entity, DatabaseObject):
            name = ".".join(
                part
                for part in (
                    entity.catalog_name,
                    entity.schema_name,
                    entity.table_name,
                    entity.column_name,
                )
                if part
            )
            yield _document(
                "DATABASE_OBJECT",
                entity,
                name,
                [
                    f"{entity.object_kind} {name}",
                    f"database: {entity.database_key} version {entity.version_key}",
                ],
                None,
            )


def _access(access: DataAccess) -> str:
    name = ".".join(
        part.normalized
        for part in (access.schema_name, access.table_name, access.column_name)
        if part
    )
    line = (
        f"{_VERBS[access.access_kind]} {access.object_kind.lower()} "
        f"{name or '(unnamed)'} as {access.role}"
    )
    return (
        line
        if access.binding_status == "BOUND"
        else f"{line} [{access.binding_status}]"
    )


def _calls(
    catalog: dict[str, Entity], outgoing: list[Relation], incoming: list[Relation]
) -> list[str]:
    def names(relations: list[Relation], end: str) -> list[str]:
        return sorted(
            {
                f"{_label(symbol)} [{relation.certainty}]"
                for relation in relations
                if isinstance(
                    symbol := catalog.get(
                        relation.source.id
                        if end == "source"
                        else relation.resolution.target.id
                    ),
                    Symbol,
                )
            }
        )

    resolved = [r for r in outgoing if r.resolution.status == "RESOLVED"]
    lines = [f"calls: {name}" for name in names(resolved, "target")]
    lines += [f"called by: {name}" for name in names(incoming, "source")]
    open_calls = Counter(
        (r.resolution.status, r.resolution.reason)
        for r in outgoing
        if r.resolution.status != "RESOLVED"
    )
    lines += [
        f"{count} {status} calls: {reason}"
        for (status, reason), count in sorted(open_calls.items())
    ]
    coverage = sorted(
        {f"{r.coverage.capability} {r.coverage.status}" for r in outgoing + incoming}
    )
    return lines + [f"coverage: {item}" for item in coverage]
