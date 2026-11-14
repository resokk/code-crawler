"""Independent, versioned database schema manifests and immutable PostgreSQL import."""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Literal, Self

import asyncpg
from pydantic import Field, model_validator

from code_crawler import datamodel
from code_crawler.ucm import ContractModel, Text, database_object_key

DbName = Annotated[str, Field(min_length=1, pattern=r"^[^\x00]+$")]
CasePolicy = Literal["EXACT", "ASCII_INSENSITIVE"]


class ColumnDefinition(ContractModel):
    name: DbName
    ordinal: int = Field(ge=1)
    data_type: Text
    nullable: bool
    primary_key: bool = False


class TableDefinition(ContractModel):
    name: DbName
    kind: Literal["TABLE", "VIEW", "MATERIALIZED_VIEW", "FOREIGN_TABLE"] = "TABLE"
    columns: tuple[ColumnDefinition, ...] = ()


class SchemaDefinition(ContractModel):
    name: DbName
    tables: tuple[TableDefinition, ...] = ()


def _fold(name: str, policy: CasePolicy) -> str:
    return name.lower() if policy == "ASCII_INSENSITIVE" and name.isascii() else name


class SchemaImport(ContractModel):
    database_key: Text
    version_key: Text
    dialect: Literal["postgres", "mysql", "tsql"]
    catalog_name: DbName
    table_case: CasePolicy = "EXACT"
    column_case: CasePolicy = "EXACT"
    coverage: Literal["COMPLETE", "PARTIAL"] = "COMPLETE"
    schemas: tuple[SchemaDefinition, ...] = ()

    @model_validator(mode="after")
    def valid_inventory(self) -> Self:
        if self.dialect == "postgres" and (
            self.table_case != "EXACT" or self.column_case != "EXACT"
        ):
            raise ValueError(
                "PostgreSQL catalog names require exact stored-name comparison"
            )
        if self.dialect == "mysql" and self.column_case != "ASCII_INSENSITIVE":
            raise ValueError(
                "MySQL column comparison requires explicit ASCII_INSENSITIVE policy"
            )

        def unique(names: list[str], policy: CasePolicy) -> None:
            folded = [_fold(name, policy) for name in names]
            if len(set(folded)) != len(folded):
                raise ValueError("duplicate/colliding schema object names")

        unique([s.name for s in self.schemas], self.table_case)
        for schema in self.schemas:
            unique([t.name for t in schema.tables], self.table_case)
            for table in schema.tables:
                unique([c.name for c in table.columns], self.column_case)
                if len({c.ordinal for c in table.columns}) != len(table.columns):
                    raise ValueError("duplicate column ordinal")
        return self

    @property
    def fingerprint(self) -> str:
        document = self.model_dump(mode="json")
        document["schemas"] = sorted(document["schemas"], key=lambda s: s["name"])
        for schema in document["schemas"]:
            schema["tables"].sort(key=lambda t: t["name"])
            for table in schema["tables"]:
                table["columns"].sort(key=lambda c: c["ordinal"])
        payload = json.dumps(
            document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class CatalogObject:
    object_key: str
    object_kind: str
    schema_name: str
    table_name: str | None
    column_name: str | None
    parent_key: str | None
    ordinal: int | None = None
    data_type: str | None = None
    nullable: bool | None = None
    primary_key: bool | None = None


def schema_objects(document: SchemaImport) -> tuple[CatalogObject, ...]:
    """Flatten a typed manifest into globally identified normalized inventory rows."""

    def key(
        kind: str, schema: str, table: str | None = None, column: str | None = None
    ) -> str:
        return database_object_key(
            document.database_key,
            document.version_key,
            kind,
            document.catalog_name,
            schema,
            table,
            column,
        )

    objects = []
    for schema in sorted(document.schemas, key=lambda s: s.name):
        parent = key("SCHEMA", schema.name)
        objects.append(CatalogObject(parent, "SCHEMA", schema.name, None, None, None))
        for table in sorted(schema.tables, key=lambda t: t.name):
            table_key = key(table.kind, schema.name, table.name)
            objects.append(
                CatalogObject(
                    table_key, table.kind, schema.name, table.name, None, parent
                )
            )
            objects.extend(
                CatalogObject(
                    key("COLUMN", schema.name, table.name, column.name),
                    "COLUMN",
                    schema.name,
                    table.name,
                    column.name,
                    table_key,
                    column.ordinal,
                    column.data_type,
                    column.nullable,
                    column.primary_key,
                )
                for column in sorted(table.columns, key=lambda c: c.ordinal)
            )
    return tuple(objects)


def _prepare_import(document: SchemaImport) -> tuple[str, list[tuple]]:
    return document.fingerprint, [
        (
            o.object_key,
            document.database_key,
            document.version_key,
            o.object_kind,
            o.schema_name,
            o.table_name,
            o.column_name,
            o.parent_key,
            o.ordinal,
            o.data_type,
            o.nullable,
            o.primary_key,
        )
        for o in schema_objects(document)
    ]


async def import_schema(conn: asyncpg.Connection, document: SchemaImport) -> str:
    """Atomically import a new immutable version; equal reimport is idempotent."""
    if conn.is_in_transaction():
        raise ValueError("schema import requires a free connection")
    fingerprint, records = await asyncio.to_thread(_prepare_import, document)
    async with conn.transaction():
        await conn.execute(
            "INSERT INTO public.ucm_database_catalogs(database_key) VALUES($1) ON CONFLICT DO NOTHING",
            document.database_key,
        )
        await conn.execute(
            "INSERT INTO public.ucm_database_schema_versions(database_key,version_key,dialect,catalog_name,table_case,column_case,coverage,fingerprint) VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT DO NOTHING",
            document.database_key,
            document.version_key,
            document.dialect,
            document.catalog_name,
            document.table_case,
            document.column_case,
            document.coverage,
            fingerprint,
        )
        current = await conn.fetchrow(
            "SELECT state,fingerprint FROM public.ucm_database_schema_versions WHERE database_key=$1 AND version_key=$2 FOR UPDATE",
            document.database_key,
            document.version_key,
        )
        if current["fingerprint"] != fingerprint:
            raise ValueError("schema version is immutable; use a new version_key")
        if current["state"] == "READY":
            return fingerprint
        if await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM public.ucm_database_schema_objects WHERE database_key=$1 AND version_key=$2)",
            document.database_key,
            document.version_key,
        ):
            raise ValueError("schema version import is not empty")
        if records:
            await conn.copy_records_to_table(
                "ucm_database_schema_objects",
                schema_name="public",
                columns=(
                    "object_key",
                    "database_key",
                    "version_key",
                    "object_kind",
                    "schema_name",
                    "table_name",
                    "column_name",
                    "parent_key",
                    "ordinal",
                    "data_type",
                    "nullable",
                    "primary_key",
                ),
                records=records,
            )
        await conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
        await conn.execute(
            "UPDATE public.ucm_database_schema_versions SET state='READY' WHERE database_key=$1 AND version_key=$2",
            document.database_key,
            document.version_key,
        )
    return fingerprint


async def load_schema(
    conn: asyncpg.Connection, database_key: str, version_key: str
) -> SchemaImport:
    """Read a complete immutable version without selecting an implicit latest version."""
    version = await conn.fetchrow(
        "SELECT * FROM public.ucm_database_schema_versions WHERE database_key=$1 AND version_key=$2 AND state='READY'",
        database_key,
        version_key,
    )
    if version is None:
        raise ValueError("unknown/unready database schema version")
    objects = await conn.fetch(
        "SELECT * FROM public.ucm_database_schema_objects WHERE database_key=$1 AND version_key=$2 ORDER BY schema_name,table_name,ordinal",
        database_key,
        version_key,
    )
    return await asyncio.to_thread(_restore_import, version, objects)


def _restore_import(
    version: asyncpg.Record, objects: list[asyncpg.Record]
) -> SchemaImport:
    database_key, version_key = version["database_key"], version["version_key"]
    schemas = []
    for schema in (o for o in objects if o["object_kind"] == "SCHEMA"):
        tables = []
        for table in (o for o in objects if o["parent_key"] == schema["object_key"]):
            columns = tuple(
                ColumnDefinition(
                    name=o["column_name"],
                    ordinal=o["ordinal"],
                    data_type=o["data_type"],
                    nullable=o["nullable"],
                    primary_key=o["primary_key"],
                )
                for o in objects
                if o["parent_key"] == table["object_key"]
            )
            tables.append(
                TableDefinition(
                    name=table["table_name"], kind=table["object_kind"], columns=columns
                )
            )
        schemas.append(
            SchemaDefinition(name=schema["schema_name"], tables=tuple(tables))
        )
    document = SchemaImport(
        database_key=database_key,
        version_key=version_key,
        dialect=version["dialect"],
        catalog_name=version["catalog_name"],
        table_case=version["table_case"],
        column_case=version["column_case"],
        coverage=version["coverage"],
        schemas=tuple(schemas),
    )
    if document.fingerprint != version["fingerprint"]:
        raise ValueError(
            "schema inventory fingerprint does not match immutable version"
        )
    return document


async def introspect_schema(
    source: asyncpg.Connection, database_key: str, version_key: str
) -> SchemaImport:
    """Reuse PostgreSQL introspection under one read-only, repeatable-read snapshot."""
    if source.is_in_transaction():
        raise ValueError("schema introspection requires a free source connection")
    async with source.transaction(isolation="repeatable_read", readonly=True):
        catalog = await source.fetchval("SELECT current_database()")
        names = await source.fetch(
            "SELECT nspname FROM pg_namespace WHERE nspname<>'information_schema' AND nspname NOT LIKE 'pg\\_%' ORDER BY nspname"
        )
        model = await datamodel.introspect(source)
    return await asyncio.to_thread(
        _from_postgres, database_key, version_key, catalog, names, model
    )


def _from_postgres(
    database_key: str,
    version_key: str,
    catalog: str,
    names: list[asyncpg.Record],
    model: datamodel.Model,
) -> SchemaImport:
    kinds = {
        "r": "TABLE",
        "p": "TABLE",
        "v": "VIEW",
        "m": "MATERIALIZED_VIEW",
        "f": "FOREIGN_TABLE",
    }
    schemas = []
    for schema in names:
        tables = []
        for table in (r for r in model.relations if r["schema"] == schema["nspname"]):
            columns = tuple(
                ColumnDefinition(
                    name=c["name"],
                    ordinal=c["position"],
                    data_type=c["data_type"],
                    nullable=c["nullable"],
                    primary_key=c["primary_key"],
                )
                for c in model.columns
                if c["table_oid"] == table["oid"]
            )
            tables.append(
                TableDefinition(
                    name=table["name"], kind=kinds[table["kind"]], columns=columns
                )
            )
        schemas.append(SchemaDefinition(name=schema["nspname"], tables=tuple(tables)))
    return SchemaImport(
        database_key=database_key,
        version_key=version_key,
        dialect="postgres",
        catalog_name=catalog,
        schemas=tuple(schemas),
    )
