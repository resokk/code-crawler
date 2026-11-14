"""Conservative database object resolution in an explicit immutable schema context."""

from dataclasses import dataclass

from pydantic import model_validator

from code_crawler.database_schema import (
    CatalogObject,
    DbName,
    SchemaImport,
    _fold,
    schema_objects,
)
from code_crawler.ucm import ContractModel, DataAccess, SqlIdentifier, Text


class ConnectionContext(ContractModel):
    connection_key: Text
    database_key: Text
    version_key: Text
    search_path: tuple[DbName, ...] = ()

    @model_validator(mode="after")
    def unique_path(self) -> "ConnectionContext":
        if len(set(self.search_path)) != len(self.search_path):
            raise ValueError("duplicate search_path entry")
        return self


class ConnectionAssignment(ContractModel):
    symbol_key: Text
    context: ConnectionContext


@dataclass(frozen=True)
class DatabaseResolution:
    status: str
    candidates: tuple[CatalogObject, ...] = ()
    reason: str | None = None


def _query_name(identifier: SqlIdentifier, dialect: str) -> str:
    return (
        identifier.text.translate(
            str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
        )
        if dialect == "postgres" and not identifier.quoted
        else identifier.text
    )


def resolve_access(
    document: SchemaImport,
    context: ConnectionContext,
    access: DataAccess,
    sql_dialect: str | None = None,
) -> DatabaseResolution:
    """Resolve only within the selected database/version and ordered schema path."""
    if (document.database_key, document.version_key) != (
        context.database_key,
        context.version_key,
    ):
        raise ValueError("database context does not match imported version")
    if sql_dialect is not None and sql_dialect != document.dialect:
        return DatabaseResolution(
            "UNRESOLVED",
            reason="SQL dialect profile differs from the database schema version",
        )
    if access.binding_status != "BOUND" or access.table_name is None:
        return DatabaseResolution(
            "AMBIGUOUS" if access.binding_status == "AMBIGUOUS" else "UNRESOLVED",
            reason="syntactic source binding is unknown/ambiguous; database identity cannot be guessed",
        )
    if (
        access.column_name is not None
        and access.column_name.text == "*"
        and not access.column_name.quoted
    ):
        return DatabaseResolution(
            "UNRESOLVED", reason="wildcard is not a single database column"
        )

    def match(actual: str, query: str, policy: str) -> bool:
        return _fold(actual, policy) == _fold(query, policy)

    names = [(document.catalog_name, document.table_case)]
    names.extend((s.name, document.table_case) for s in document.schemas)
    names.extend(
        (t.name, document.table_case) for s in document.schemas for t in s.tables
    )
    if access.column_name is not None:
        names.extend(
            (c.name, document.column_case)
            for s in document.schemas
            for t in s.tables
            for c in t.columns
        )
    query_names = [
        (access.catalog_name, document.table_case),
        (access.schema_name, document.table_case),
        (access.table_name, document.table_case),
        (access.column_name, document.column_case),
    ]
    if any(
        policy == "ASCII_INSENSITIVE" and not name.isascii() for name, policy in names
    ) or any(
        identifier is not None
        and policy == "ASCII_INSENSITIVE"
        and not identifier.text.isascii()
        for identifier, policy in query_names
    ):
        return DatabaseResolution(
            "UNRESOLVED",
            reason="configured ASCII case policy cannot prove Unicode/collation equivalence",
        )
    if access.catalog_name is not None and not match(
        document.catalog_name,
        _query_name(access.catalog_name, document.dialect),
        document.table_case,
    ):
        return DatabaseResolution(
            "UNRESOLVED",
            reason="SQL catalog qualifier is outside the selected database context",
        )
    requested_schema = (
        _query_name(access.schema_name, document.dialect)
        if access.schema_name
        else None
    )
    path = (requested_schema,) if requested_schema is not None else context.search_path
    if not path:
        return DatabaseResolution(
            "UNRESOLVED",
            reason="unqualified table requires an explicit schema search_path",
        )
    requested_table = _query_name(access.table_name, document.dialect)
    unknown_earlier = False
    for entry in path:
        schema = next(
            (s for s in document.schemas if match(s.name, entry, document.table_case)),
            None,
        )
        table = (
            next(
                (
                    t
                    for t in schema.tables
                    if match(t.name, requested_table, document.table_case)
                ),
                None,
            )
            if schema
            else None
        )
        if table is None:
            if document.coverage == "PARTIAL" or (
                schema is None
                and document.dialect == "postgres"
                and (
                    entry.startswith("pg_") or entry in ("information_schema", "$user")
                )
            ):
                unknown_earlier = True
            continue
        objects = schema_objects(document)
        if access.object_kind == "TABLE":
            target = next(
                o
                for o in objects
                if o.schema_name == schema.name
                and o.table_name == table.name
                and o.object_kind == table.kind
            )
        else:
            column_name = _query_name(access.column_name, document.dialect)
            column = next(
                (
                    c
                    for c in table.columns
                    if match(c.name, column_name, document.column_case)
                ),
                None,
            )
            if column is None:
                return DatabaseResolution(
                    "UNRESOLVED",
                    reason="column is absent or not covered in the selected schema version",
                )
            target = next(
                o
                for o in objects
                if o.schema_name == schema.name
                and o.table_name == table.name
                and o.column_name == column.name
            )
        if unknown_earlier:
            return DatabaseResolution(
                "PARTIAL",
                (target,),
                "an earlier search_path schema/table may be omitted from the partial inventory",
            )
        return DatabaseResolution("RESOLVED", (target,))
    return DatabaseResolution(
        "UNRESOLVED",
        reason="table is absent or not covered in the selected schema version/search_path",
    )
