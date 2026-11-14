import pytest
from pydantic import ValidationError

from code_crawler.database_resolution import ConnectionContext, resolve_access
from code_crawler.database_schema import (
    ColumnDefinition,
    SchemaDefinition,
    SchemaImport,
    TableDefinition,
    schema_objects,
)
from code_crawler.sql_semantic import analyze_statements
from code_crawler.ucm import DataAccess, EntityType, database_object_key, logical_id


def schema(
    database_key: str = "orders-prod",
    version_key: str = "v1",
    coverage: str = "COMPLETE",
) -> SchemaImport:
    columns = (
        ColumnDefinition(
            name="id", ordinal=1, data_type="integer", nullable=False, primary_key=True
        ),
        ColumnDefinition(name="Name", ordinal=3, data_type="text", nullable=True),
    )
    return SchemaImport(
        database_key=database_key,
        version_key=version_key,
        dialect="postgres",
        catalog_name="orders",
        coverage=coverage,
        schemas=(
            SchemaDefinition(
                name="public",
                tables=(
                    TableDefinition(name="users", columns=columns),
                    TableDefinition(name="Users", columns=columns),
                ),
            ),
            SchemaDefinition(
                name="tenant", tables=(TableDefinition(name="users", columns=columns),)
            ),
        ),
    )


def access(
    query: str,
    kind: str = "TABLE",
    column: str | None = None,
    dialect: str = "postgres",
) -> DataAccess:
    detail = next(
        a
        for a in analyze_statements(query, dialect)[0].accesses
        if a.object_kind == kind and (column is None or a.column_name.text == column)
    )
    return DataAccess(
        repository_id="repo",
        logical_key="access",
        name="access",
        id=logical_id("repo", EntityType.DATA_ACCESS, "access"),
        statement_id=logical_id("repo", EntityType.SQL_STATEMENT, "statement"),
        **detail.model_dump(),
    )


def context(
    document: SchemaImport, path: tuple[str, ...] = ("public",)
) -> ConnectionContext:
    return ConnectionContext(
        connection_key="primary",
        database_key=document.database_key,
        version_key=document.version_key,
        search_path=path,
    )


def test_global_object_identity_separates_databases_versions_and_schemas() -> None:
    keys = {
        database_object_key(db, version, "TABLE", "orders", schema_name, "users")
        for db in ("prod", "test")
        for version in ("v1", "v2")
        for schema_name in ("public", "tenant")
    }
    assert len(keys) == 8
    assert len({o.object_key for o in schema_objects(schema())}) == len(
        schema_objects(schema())
    )


def test_unqualified_name_uses_explicit_ordered_path() -> None:
    document = schema()
    assert (
        resolve_access(
            document,
            context(document, ("tenant", "public")),
            access("select id from users"),
        )
        .candidates[0]
        .schema_name
        == "tenant"
    )
    assert (
        resolve_access(document, context(document), access("select id from users"))
        .candidates[0]
        .schema_name
        == "public"
    )


def test_absent_search_path_is_not_guessed_from_unique_table() -> None:
    document = schema()
    assert (
        resolve_access(
            document, context(document, ()), access("select id from users")
        ).status
        == "UNRESOLVED"
    )
    assert (
        resolve_access(
            document, context(document, ()), access("select id from tenant.users")
        ).status
        == "RESOLVED"
    )


def test_quoted_postgres_names_and_column_case() -> None:
    document = schema()
    quoted = resolve_access(
        document,
        context(document),
        access('select "Name" from "Users"', "COLUMN", "Name"),
    )
    assert quoted.status == "RESOLVED" and quoted.candidates[0].table_name == "Users"
    assert (
        resolve_access(
            document,
            context(document),
            access("select name from users", "COLUMN", "name"),
        ).status
        == "UNRESOLVED"
    )
    assert (
        resolve_access(document, context(document), access("select id from Users"))
        .candidates[0]
        .table_name
        == "users"
    )


def test_cross_catalog_does_not_select_another_database() -> None:
    document = schema()
    assert (
        resolve_access(
            document, context(document), access("select id from other.public.users")
        ).status
        == "UNRESOLVED"
    )
    assert (
        resolve_access(
            document, context(document), access("select id from orders.public.users")
        ).status
        == "RESOLVED"
    )


def test_versions_resolve_only_explicit_context() -> None:
    with pytest.raises(ValueError, match="does not match"):
        resolve_access(
            schema(), context(schema(version_key="v2")), access("select id from users")
        )


def test_complete_and_partial_search_path_precedence() -> None:
    complete = schema()
    partial = schema(coverage="PARTIAL")
    query = access("select id from users")
    assert (
        resolve_access(complete, context(complete, ("missing", "public")), query).status
        == "RESOLVED"
    )
    result = resolve_access(partial, context(partial, ("missing", "public")), query)
    assert result.status == "PARTIAL" and result.candidates[0].schema_name == "public"
    assert resolve_access(partial, context(partial), query).status == "RESOLVED"


def test_absent_table_column_and_star_are_not_fabricated() -> None:
    document = schema()
    assert (
        resolve_access(
            document, context(document), access("select id from missing")
        ).status
        == "UNRESOLVED"
    )
    assert (
        resolve_access(
            document,
            context(document),
            access("select missing from users", "COLUMN", "missing"),
        ).status
        == "UNRESOLVED"
    )
    assert (
        resolve_access(
            document,
            context(document),
            access("select users.* from users", "COLUMN", "*"),
        ).status
        == "UNRESOLVED"
    )


def test_ambiguous_syntactic_binding_remains_ambiguous() -> None:
    document = schema()
    query = access(
        "select id from users join tenant.users u on users.id=u.id", "COLUMN", "id"
    )
    # Pick the unqualified SELECT access, not one of the qualified ON operands.
    detail = next(
        a
        for a in analyze_statements(
            "select id from users join tenant.users u on users.id=u.id"
        )[0].accesses
        if a.binding_status == "AMBIGUOUS"
    )
    query = DataAccess(**{**query.model_dump(), **detail.model_dump()})
    assert resolve_access(document, context(document), query).status == "AMBIGUOUS"


def test_dialect_mismatch_is_explicit() -> None:
    document = schema()
    assert (
        resolve_access(
            document,
            context(document),
            access("select id from users"),
            sql_dialect="mysql",
        ).status
        == "UNRESOLVED"
    )


def test_manifest_fingerprint_is_order_independent_and_includes_metadata() -> None:
    document = schema()
    reordered = document.model_copy(
        update={"schemas": tuple(reversed(document.schemas))}
    )
    assert document.fingerprint == reordered.fingerprint
    assert document.fingerprint != schema(version_key="v2").fingerprint


def test_duplicate_names_and_ordinals_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        SchemaImport(
            **{
                **schema().model_dump(),
                "schemas": (schema().schemas[0], schema().schemas[0]),
            }
        )
    table = TableDefinition(
        name="users",
        columns=(
            ColumnDefinition(name="id", ordinal=1, data_type="int", nullable=False),
            ColumnDefinition(name="other", ordinal=1, data_type="int", nullable=False),
        ),
    )
    with pytest.raises(ValidationError, match="ordinal"):
        SchemaImport(
            database_key="d",
            version_key="v",
            dialect="postgres",
            catalog_name="d",
            schemas=(SchemaDefinition(name="public", tables=(table,)),),
        )


def test_mysql_explicit_case_policy_and_unicode_limit() -> None:
    table = TableDefinition(
        name="Users",
        columns=(
            ColumnDefinition(name="ID", ordinal=1, data_type="int", nullable=False),
        ),
    )
    document = SchemaImport(
        database_key="db",
        version_key="v",
        dialect="mysql",
        catalog_name="db",
        table_case="ASCII_INSENSITIVE",
        column_case="ASCII_INSENSITIVE",
        schemas=(SchemaDefinition(name="Main", tables=(table,)),),
    )
    assert (
        resolve_access(
            document,
            context(document, ("main",)),
            access("select id from users", "COLUMN", "id", "mysql"),
        ).status
        == "RESOLVED"
    )
    unicode_table = table.model_copy(update={"name": "Пользователи"})
    unicode_doc = document.model_copy(
        update={"schemas": (SchemaDefinition(name="Main", tables=(unicode_table,)),)}
    )
    result = resolve_access(
        unicode_doc,
        context(unicode_doc, ("main",)),
        access("select id from users", dialect="mysql"),
    )
    assert result.status == "UNRESOLVED" and "Unicode" in result.reason


def test_postgres_policy_cannot_casefold_quoted_names() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        SchemaImport(
            database_key="d",
            version_key="v",
            dialect="postgres",
            catalog_name="d",
            table_case="ASCII_INSENSITIVE",
        )


def test_postgres_utf8_non_ascii_stored_names_are_not_unicode_casefolded() -> None:
    document = SchemaImport(
        database_key="d",
        version_key="v",
        dialect="postgres",
        catalog_name="d",
        schemas=(
            SchemaDefinition(
                name="public", tables=(TableDefinition(name="Пользователи"),)
            ),
        ),
    )
    assert (
        resolve_access(
            document, context(document), access("select id from Пользователи")
        ).status
        == "RESOLVED"
    )


def test_excluded_session_system_schemas_do_not_prove_public_precedence() -> None:
    document = schema()
    result = resolve_access(
        document,
        context(document, ("pg_temp", "public")),
        access("select id from users"),
    )
    assert result.status == "PARTIAL" and result.candidates[0].schema_name == "public"
