"""Слой данных: структура прикладной БД, прочитанная из её системного каталога."""

from dataclasses import dataclass

import asyncpg

_KINDS = {
    "r": "table",
    "p": "table",
    "v": "view",
    "m": "materialized view",
    "f": "foreign table",
}

_RELATIONS = """
    SELECT c.oid::bigint AS oid, n.nspname AS schema, c.relname AS name,
           c.relkind::text AS kind, obj_description(c.oid, 'pg_class') AS comment
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f')
      AND n.nspname <> 'information_schema'
      AND n.nspname NOT LIKE 'pg\\_%'
    ORDER BY n.nspname, c.relname
"""

_COLUMNS = """
    SELECT a.attrelid::bigint AS table_oid, a.attname AS name, a.attnum::int AS position,
           format_type(a.atttypid, a.atttypmod) AS data_type,
           NOT a.attnotnull AS nullable,
           COALESCE(a.attnum = ANY (i.indkey), false) AS primary_key,
           col_description(a.attrelid, a.attnum) AS comment
    FROM pg_attribute a
    LEFT JOIN pg_index i ON i.indrelid = a.attrelid AND i.indisprimary
    WHERE a.attrelid = ANY ($1::oid[]) AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY a.attrelid, a.attnum
"""

_FOREIGN_KEYS = """
    SELECT c.conname AS name,
           c.conrelid::bigint AS table_oid, k.attnum::int AS position,
           c.confrelid::bigint AS ref_table_oid, k.ref_attnum::int AS ref_position
    FROM pg_constraint c
    CROSS JOIN LATERAL unnest(c.conkey, c.confkey) AS k (attnum, ref_attnum)
    WHERE c.contype = 'f'
      AND c.conrelid = ANY ($1::oid[]) AND c.confrelid = ANY ($1::oid[])
"""


@dataclass
class Model:
    relations: list[asyncpg.Record]
    columns: list[asyncpg.Record]
    foreign_keys: list[asyncpg.Record]


async def introspect(conn: asyncpg.Connection) -> Model:
    """Читает таблицы, представления, колонки и внешние ключи всех несистемных схем."""
    relations = await conn.fetch(_RELATIONS)
    oids = [relation["oid"] for relation in relations]
    return Model(
        relations,
        await conn.fetch(_COLUMNS, oids),
        await conn.fetch(_FOREIGN_KEYS, oids),
    )


async def store(conn: asyncpg.Connection, model: Model) -> None:
    """Заменяет слой данных целиком, в одной транзакции."""
    async with conn.transaction():
        await conn.execute("DELETE FROM data_tables")
        table_ids = dict(
            zip(
                (relation["oid"] for relation in model.relations),
                await _ids(conn, "data_tables", len(model.relations)),
                strict=True,
            )
        )
        await conn.copy_records_to_table(
            "data_tables",
            columns=("id", "schema", "name", "kind", "comment"),
            records=[
                (
                    table_ids[r["oid"]],
                    r["schema"],
                    r["name"],
                    _KINDS[r["kind"]],
                    r["comment"],
                )
                for r in model.relations
            ],
        )
        column_ids = dict(
            zip(
                ((c["table_oid"], c["position"]) for c in model.columns),
                await _ids(conn, "data_columns", len(model.columns)),
                strict=True,
            )
        )
        await conn.copy_records_to_table(
            "data_columns",
            columns=(
                "id",
                "table_id",
                "name",
                "position",
                "data_type",
                "nullable",
                "primary_key",
                "comment",
            ),
            records=[
                (
                    column_ids[c["table_oid"], c["position"]],
                    table_ids[c["table_oid"]],
                    c["name"],
                    c["position"],
                    c["data_type"],
                    c["nullable"],
                    c["primary_key"],
                    c["comment"],
                )
                for c in model.columns
            ],
        )
        await conn.copy_records_to_table(
            "data_foreign_keys",
            columns=("name", "column_id", "ref_column_id"),
            records=[
                (
                    fk["name"],
                    column_ids[fk["table_oid"], fk["position"]],
                    column_ids[fk["ref_table_oid"], fk["ref_position"]],
                )
                for fk in model.foreign_keys
            ],
        )


async def _ids(conn: asyncpg.Connection, table: str, count: int) -> list[int]:
    rows = await conn.fetch(
        "SELECT nextval(pg_get_serial_sequence($1, 'id')) FROM generate_series(1, $2)",
        table,
        count,
    )
    return [row[0] for row in rows]
