"""Read-only structural queries over the published UCM snapshot of a repository."""

from typing import Literal
from uuid import UUID

import asyncpg

from code_crawler import external_candidates
from code_crawler.resolver_context import ResolverContext
from code_crawler.snapshots import pin_snapshot

MAX_LIMIT = 200
MAX_DEPTH = 6

MAX_OFFSET = 1000
# Тот же список — в предикате частичных индексов миграции 0019.
TEXT_TYPES = ("SYMBOL", "SOURCE_FILE", "DATABASE_OBJECT", "ORM_MAPPING", "ORM_QUERY")

_WRITES = ("INSERT", "UPDATE", "DELETE", "MERGE", "DDL")


def _limit(limit: int) -> int:
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    return limit


async def _snapshot(
    conn: asyncpg.Connection, repository_key: str, snapshot_id: UUID | None = None
) -> UUID:
    if snapshot_id is not None:
        # Явная версия — только та, что была опубликована: BUILDING/READY не читаются.
        if not await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM public.ucm_snapshots s "
            "JOIN public.ucm_repositories r ON r.id=s.repository_id "
            "WHERE s.id=$2 AND r.repository_key=$1 AND s.state IN ('PUBLISHED','RETIRED'))",
            repository_key,
            snapshot_id,
        ):
            raise ValueError("snapshot is not a published version of the repository")
        if conn.is_in_transaction():
            await pin_snapshot(conn, snapshot_id)
        return snapshot_id
    snapshot_id = await conn.fetchval(
        "SELECT p.snapshot_id FROM public.ucm_repository_publications p "
        "JOIN public.ucm_repositories r ON r.id=p.repository_id WHERE r.repository_key=$1",
        repository_key,
    )
    if snapshot_id is None:
        raise ValueError("repository has no published snapshot")
    if conn.is_in_transaction():
        await pin_snapshot(conn, snapshot_id)
    return snapshot_id


def _page(snapshot_id: UUID, items: list, rows: list, limit: int) -> dict:
    """Queries fetch limit+1 rows, so a cut result is reported instead of looking whole."""
    return {
        "snapshot_id": str(snapshot_id),
        "items": items[:limit],
        "truncated": len(rows) > limit,
    }


async def _entities(
    conn: asyncpg.Connection, snapshot_id: UUID, ids: set[str | None]
) -> dict[str, dict]:
    rows = await conn.fetch(
        "SELECT e.entity_id AS id, e.entity_type AS type, e.name, s.symbol_kind AS kind, "
        "s.qualified_name, COALESCE(f.path, own.path) AS path, e.start_line, e.end_line, "
        "(SELECT array_agg(t.name ORDER BY t.position) FROM public.ucm_type_refs t "
        " WHERE t.snapshot_id=e.snapshot_id AND t.owner_id=e.entity_id "
        " AND t.role='PARAMETER') AS parameter_types "
        "FROM public.ucm_entities e "
        # OFFSET 0 не даёт планировщику заменить поиск по ключу на hash join с
        # полным чтением ucm_symbols: PostgreSQL 15 выбирал его для страницы результатов.
        "LEFT JOIN LATERAL (SELECT y.symbol_kind, y.qualified_name "
        " FROM public.ucm_symbols y WHERE y.snapshot_id=e.snapshot_id "
        " AND y.entity_id=e.entity_id OFFSET 0) s ON true "
        "LEFT JOIN public.ucm_source_files f ON f.snapshot_id=e.snapshot_id "
        " AND f.entity_id=e.source_file_id "
        # Сам файл: у SOURCE_FILE нет source_file_id, его путь — в собственной строке.
        "LEFT JOIN public.ucm_source_files own ON own.snapshot_id=e.snapshot_id "
        " AND own.entity_id=e.entity_id "
        "WHERE e.snapshot_id=$1 AND e.entity_id=ANY($2)",
        snapshot_id,
        [i for i in ids if i],
    )
    return {row["id"]: {k: v for k, v in row.items() if v is not None} for row in rows}


async def _proofs(
    conn: asyncpg.Connection, snapshot_id: UUID, owner_ids: list[str]
) -> dict[str, dict]:
    """Evidence, coverage reasons and unresolved candidates of relations."""
    result: dict[str, dict] = {
        owner: {"evidence": [], "coverage_reasons": [], "candidates": []}
        for owner in owner_ids
    }
    for row in await conn.fetch(
        "SELECT v.owner_id, f.path, v.start_line, v.start_byte_column, v.end_line, "
        "v.end_byte_column, v.analyzer, v.analyzer_version, v.rule, v.description "
        "FROM public.ucm_evidence v JOIN public.ucm_source_files f "
        "ON f.snapshot_id=v.snapshot_id AND f.entity_id=v.source_file_id "
        "WHERE v.snapshot_id=$1 AND v.owner_id=ANY($2) ORDER BY v.owner_id, v.ordinal",
        snapshot_id,
        owner_ids,
    ):
        evidence = dict(row)
        result[evidence.pop("owner_id")]["evidence"].append(evidence)
    for row in await conn.fetch(
        "SELECT owner_id, reason FROM public.ucm_coverage_reasons "
        "WHERE snapshot_id=$1 AND owner_id=ANY($2) ORDER BY owner_id, ordinal",
        snapshot_id,
        owner_ids,
    ):
        result[row["owner_id"]]["coverage_reasons"].append(row["reason"])
    for row in await conn.fetch(
        "SELECT relation_id, candidate_id FROM public.ucm_relation_candidates "
        "WHERE snapshot_id=$1 AND relation_id=ANY($2) ORDER BY relation_id, candidate_id",
        snapshot_id,
        owner_ids,
    ):
        result[row["relation_id"]]["candidates"].append(row["candidate_id"])
    return result


_RELATION = (
    "r.entity_id AS relation_id, r.relation_kind, r.source_id, r.target_id, "
    "r.resolution, r.reason, r.certainty, r.coverage_capability, "
    "r.coverage_analyzer_version, r.coverage_status"
)


async def _relations(
    conn: asyncpg.Connection, snapshot_id: UUID, rows: list[asyncpg.Record]
) -> list[dict]:
    """Attach endpoints, Evidence and Coverage to relation rows."""
    proofs = await _proofs(conn, snapshot_id, [row["relation_id"] for row in rows])
    ids = {row["source_id"] for row in rows} | {row["target_id"] for row in rows}
    for proof in proofs.values():
        ids.update(proof["candidates"])
    entities = await _entities(conn, snapshot_id, ids)
    items = []
    for row in rows:
        proof = proofs[row["relation_id"]]
        item = {
            "relation_id": row["relation_id"],
            "relation_kind": row["relation_kind"],
            "source": entities[row["source_id"]],
            "target": entities.get(row["target_id"]),
            "resolution": row["resolution"],
            "certainty": row["certainty"],
            "coverage": {
                "capability": row["coverage_capability"],
                "analyzer_version": row["coverage_analyzer_version"],
                "status": row["coverage_status"],
                "reasons": proof["coverage_reasons"],
            },
            "evidence": proof["evidence"],
        }
        if row["reason"]:
            item["reason"] = row["reason"]
        if proof["candidates"]:
            item["candidates"] = [entities[c] for c in proof["candidates"]]
        if row.get("depth") is not None:
            item["depth"] = row["depth"]
        items.append(item)
    return items


async def search_symbols(
    conn: asyncpg.Connection,
    repository_key: str,
    name: str,
    *,
    kind: str | None = None,
    parameter_types: list[str] | None = None,
    limit: int = 50,
) -> dict:
    """Find symbols by exact simple or qualified name, optionally by kind and signature."""
    snapshot_id = await _snapshot(conn, repository_key)
    rows = await conn.fetch(
        # UNION вместо OR по двум таблицам: каждая ветка идёт по своему индексу.
        # OFFSET 0: каждый найденный ID читается по ключу, см. _entities.
        "SELECT s.entity_id FROM ("
        " SELECT entity_id FROM public.ucm_entities "
        " WHERE snapshot_id=$1 AND entity_type='SYMBOL' AND name=$2 "
        " UNION SELECT entity_id FROM public.ucm_symbols "
        " WHERE snapshot_id=$1 AND qualified_name=$2) m "
        "JOIN LATERAL (SELECT y.* FROM public.ucm_symbols y "
        " WHERE y.snapshot_id=$1 AND y.entity_id=m.entity_id OFFSET 0) s ON true "
        "WHERE ($3::text IS NULL OR s.symbol_kind=$3) "
        "AND ($4::text[] IS NULL OR $4 = COALESCE((SELECT array_agg(t.name ORDER BY t.position) "
        " FROM public.ucm_type_refs t WHERE t.snapshot_id=s.snapshot_id "
        " AND t.owner_id=s.entity_id AND t.role='PARAMETER'), '{}')) "
        "ORDER BY s.qualified_name, s.entity_id LIMIT $5",
        snapshot_id,
        name,
        kind,
        parameter_types,
        _limit(limit) + 1,
    )
    entities = await _entities(conn, snapshot_id, {row["entity_id"] for row in rows})
    return _page(snapshot_id, [entities[row["entity_id"]] for row in rows], rows, limit)


async def search_text(
    conn: asyncpg.Connection,
    repository_key: str,
    query: str,
    *,
    entity_types: list[str] | None = None,
    snapshot_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Fuzzy identifier search: exact name, then all query words, then similar spelling.

    Query and names are split into words on case changes and punctuation, so
    "user id" finds getUserId and user_id.
    """
    if not query.strip():
        raise ValueError("query must not be blank")
    if not 0 <= offset <= MAX_OFFSET:
        raise ValueError(f"offset must be between 0 and {MAX_OFFSET}")
    types = tuple(entity_types or TEXT_TYPES)
    if not set(types) <= set(TEXT_TYPES):
        raise ValueError("entity_types must be among " + ", ".join(TEXT_TYPES))
    snapshot_id = await _snapshot(conn, repository_key, snapshot_id)
    # Литералы из фиксированного списка: по ним планировщик выбирает частичные индексы.
    listed = ",".join(f"'{entity_type}'" for entity_type in types)
    like = "%" + query.lower().translate({ord(c): "\\" + c for c in "\\%_"}) + "%"
    words = "plainto_tsquery('simple', public.ucm_identifier_words($2))"
    name_words = "to_tsvector('simple', public.ucm_identifier_words(e.name))"
    qualified_words = (
        "to_tsvector('simple', public.ucm_identifier_words(s.qualified_name))"
    )
    rows = await conn.fetch(
        "WITH hits AS ("
        " SELECT e.entity_id FROM public.ucm_entities e WHERE e.snapshot_id=$1 "
        f" AND e.entity_type IN ({listed}) AND (lower(e.name) % lower($2) "
        f"  OR lower(e.name) LIKE $3 OR {name_words} @@ {words}) "
        " UNION SELECT s.entity_id FROM public.ucm_symbols s WHERE s.snapshot_id=$1 "
        f" AND 'SYMBOL' IN ({listed}) AND {qualified_words} @@ {words}) "
        "SELECT * FROM (SELECT e.entity_id, CASE "
        " WHEN lower($2) IN (lower(e.name), lower(s.qualified_name)) THEN 'EXACT' "
        f" WHEN {name_words} @@ {words} OR {qualified_words} @@ {words} THEN 'WORDS' "
        " ELSE 'SIMILAR' END AS match, "
        "similarity(lower(e.name), lower($2)) AS similarity, "
        "COALESCE(s.qualified_name, e.name) AS label "
        "FROM hits JOIN public.ucm_entities e ON e.snapshot_id=$1 "
        " AND e.entity_id=hits.entity_id "
        "LEFT JOIN public.ucm_symbols s ON s.snapshot_id=$1 "
        " AND s.entity_id=e.entity_id) ranked "
        "ORDER BY array_position(ARRAY['EXACT','WORDS','SIMILAR'], match), "
        "similarity DESC, label, entity_id LIMIT $4 OFFSET $5",
        snapshot_id,
        query,
        like,
        _limit(limit) + 1,
        offset,
    )
    entities = await _entities(conn, snapshot_id, {row["entity_id"] for row in rows})
    page = _page(
        snapshot_id,
        [
            entities[row["entity_id"]]
            | {"match": row["match"], "similarity": round(row["similarity"], 3)}
            for row in rows
        ],
        rows,
        limit,
    )
    # Курсор — смещение в детерминированном порядке; None, когда страниц больше нет.
    page["next_offset"] = offset + limit if page["truncated"] else None
    return page


async def _calls(
    conn: asyncpg.Connection,
    repository_key: str,
    symbol_id: str,
    own: str,
    limit: int,
) -> dict:
    snapshot_id = await _snapshot(conn, repository_key)
    matched = (
        f"SELECT entity_id FROM public.ucm_relations WHERE snapshot_id=$1 "
        f"AND relation_kind='CALLS' AND {own}=$2"
    )
    if own == "target_id":
        # Кандидаты AMBIGUOUS/PARTIAL связей — тоже возможные вызовы: их нельзя терять молча.
        matched += (
            " UNION ALL SELECT relation_id FROM public.ucm_relation_candidates "
            "WHERE snapshot_id=$1 AND candidate_id=$2"
        )
    rows = await conn.fetch(
        f"SELECT {_RELATION} FROM public.ucm_relations r WHERE r.snapshot_id=$1 "
        f"AND r.relation_kind='CALLS' AND r.entity_id IN ({matched}) "
        "ORDER BY r.entity_id LIMIT $3",
        snapshot_id,
        symbol_id,
        _limit(limit) + 1,
    )
    return _page(
        snapshot_id, await _relations(conn, snapshot_id, rows[:limit]), rows, limit
    )


async def find_callers(
    conn: asyncpg.Connection, repository_key: str, symbol_id: str, *, limit: int = 50
) -> dict:
    """Return CALLS relations targeting the symbol, including ambiguous candidates."""
    return await _calls(conn, repository_key, symbol_id, "target_id", limit)


async def find_callees(
    conn: asyncpg.Connection, repository_key: str, symbol_id: str, *, limit: int = 50
) -> dict:
    """Return CALLS relations from the symbol; unresolved calls keep their reason."""
    return await _calls(conn, repository_key, symbol_id, "source_id", limit)


async def _executions(
    conn: asyncpg.Connection, snapshot_id: UUID, where: str, *arguments: object
) -> list[dict]:
    rows = await conn.fetch(
        "SELECT x.entity_id AS id, x.api, x.owner_symbol_id, o.qualified_name AS owner, "
        "f.path, e.start_line, e.end_line FROM public.ucm_sql_executions x "
        "JOIN public.ucm_entities e USING (snapshot_id, entity_id) "
        "JOIN LATERAL (SELECT y.qualified_name FROM public.ucm_symbols y "
        " WHERE y.snapshot_id=x.snapshot_id AND y.entity_id=x.owner_symbol_id "
        " OFFSET 0) o ON true "
        "LEFT JOIN public.ucm_source_files f ON f.snapshot_id=e.snapshot_id "
        " AND f.entity_id=e.source_file_id "
        f"WHERE x.snapshot_id=$1 AND {where}",
        snapshot_id,
        *arguments,
    )
    return [dict(row) for row in rows]


async def find_sql_executions(
    conn: asyncpg.Connection,
    repository_key: str,
    *,
    symbol_id: str | None = None,
    limit: int = 50,
) -> dict:
    """List SQL execution sinks, optionally of one owner symbol, with their statements."""
    snapshot_id = await _snapshot(conn, repository_key)
    executions = await _executions(
        conn,
        snapshot_id,
        "($2::text IS NULL OR x.owner_symbol_id=$2) ORDER BY x.entity_id LIMIT $3",
        symbol_id,
        _limit(limit) + 1,
    )
    page = executions[:limit]
    rows = await conn.fetch(
        f"SELECT {_RELATION}, st.text, st.operation, st.parse_status, st.dialect "
        "FROM public.ucm_relations r JOIN public.ucm_sql_statements st "
        "ON st.snapshot_id=r.snapshot_id AND st.entity_id=r.target_id "
        "WHERE r.snapshot_id=$1 AND r.relation_kind='EXECUTES_STATEMENT' "
        "AND r.source_id=ANY($2) ORDER BY r.entity_id",
        snapshot_id,
        [execution["id"] for execution in page],
    )
    relations = await _relations(conn, snapshot_id, rows)
    for execution in page:
        # Пустой список — sink найден, но его SQL-текст статически не восстановлен.
        execution["statements"] = [
            {
                "statement_id": row["target_id"],
                "text": row["text"],
                "operation": row["operation"],
                "parse_status": row["parse_status"],
                "dialect": row["dialect"],
                "relation": relation,
            }
            for row, relation in zip(rows, relations, strict=True)
            if row["source_id"] == execution["id"]
        ]
    return _page(snapshot_id, executions, executions, limit)


async def _accesses(
    conn: asyncpg.Connection,
    repository_key: str,
    table: str,
    column: str | None,
    schema: str | None,
    kinds: tuple[str, ...],
    limit: int,
) -> dict:
    snapshot_id = await _snapshot(conn, repository_key)

    def named(part: str, index: int) -> str:
        return (
            "EXISTS (SELECT 1 FROM public.ucm_sql_access_names n "
            "WHERE n.snapshot_id=a.snapshot_id AND n.access_id=a.entity_id "
            f"AND n.part='{part}' AND n.normalized IN (${index}, lower(${index})))"
        )

    rows = await conn.fetch(
        "SELECT a.entity_id AS access_id, a.object_kind, a.access_kind, a.role, "
        "a.binding_status, a.resolution, a.reason, a.statement_id, st.text, st.operation, "
        "st.parse_status FROM public.ucm_data_accesses a "
        "JOIN public.ucm_sql_statements st ON st.snapshot_id=a.snapshot_id "
        " AND st.entity_id=a.statement_id "
        # JOIN, а не EXISTS: поиск начинается с индекса по нормализованному имени.
        "JOIN public.ucm_sql_access_names tn ON tn.snapshot_id=a.snapshot_id "
        " AND tn.access_id=a.entity_id AND tn.part='table_name' "
        " AND tn.normalized IN ($3, lower($3)) "
        "WHERE a.snapshot_id=$1 AND a.access_kind=ANY($2) "
        "AND a.object_kind=CASE WHEN $4::text IS NULL THEN 'TABLE' ELSE 'COLUMN' END "
        f"AND ($4::text IS NULL OR {named('column_name', 4)}) "
        f"AND ($5::text IS NULL OR {named('schema_name', 5)}) "
        "ORDER BY a.entity_id LIMIT $6",
        snapshot_id,
        list(kinds),
        table,
        column,
        schema,
        _limit(limit) + 1,
    )
    page = rows[:limit]
    links = await conn.fetch(
        "SELECT r.target_id AS statement_id, r.source_id AS execution_id, r.certainty "
        "FROM public.ucm_relations r WHERE r.snapshot_id=$1 "
        "AND r.relation_kind='EXECUTES_STATEMENT' AND r.target_id=ANY($2)",
        snapshot_id,
        list({row["statement_id"] for row in page}),
    )
    executions = {
        execution["id"]: execution
        for execution in await _executions(
            conn,
            snapshot_id,
            "x.entity_id=ANY($2)",
            list({link["execution_id"] for link in links}),
        )
    }
    items = []
    for row in page:
        item = dict(row)
        # Пустой список — SQL найден в коде, но его выполнение не доказано.
        item["executions"] = [
            executions[link["execution_id"]] | {"certainty": link["certainty"]}
            for link in links
            if link["statement_id"] == row["statement_id"]
        ]
        items.append(item)
    return _page(snapshot_id, items, rows, limit)


async def find_table_readers(
    conn: asyncpg.Connection,
    repository_key: str,
    table: str,
    *,
    column: str | None = None,
    schema: str | None = None,
    limit: int = 50,
) -> dict:
    """Find SQL statements reading a table (or one of its columns) and who executes them."""
    return await _accesses(
        conn, repository_key, table, column, schema, ("READ",), limit
    )


async def find_table_writers(
    conn: asyncpg.Connection,
    repository_key: str,
    table: str,
    *,
    column: str | None = None,
    schema: str | None = None,
    limit: int = 50,
) -> dict:
    """Find SQL statements writing a table (or one of its columns) and who executes them."""
    return await _accesses(conn, repository_key, table, column, schema, _WRITES, limit)


async def trace_dependency(
    conn: asyncpg.Connection,
    repository_key: str,
    entity_id: str,
    *,
    direction: Literal["out", "in"] = "out",
    relation_kinds: list[str] | None = None,
    depth: int = 2,
    limit: int = 100,
) -> dict:
    """Walk relations from an entity to a bounded depth.

    Unresolved relations are returned (outward) but not followed.
    """
    if not 1 <= depth <= MAX_DEPTH:
        raise ValueError(f"depth must be between 1 and {MAX_DEPTH}")
    if direction not in ("out", "in"):
        raise ValueError("direction must be 'out' or 'in'")
    near, far = (
        ("source_id", "target_id") if direction == "out" else ("target_id", "source_id")
    )
    snapshot_id = await _snapshot(conn, repository_key)
    rows = await conn.fetch(
        "WITH RECURSIVE walk(entity_id, depth) AS ("
        " SELECT $2::text, 0 UNION "
        f" SELECT r.{far}, w.depth+1 FROM walk w JOIN public.ucm_relations r "
        f" ON r.snapshot_id=$1 AND r.{near}=w.entity_id "
        " AND ($4::text[] IS NULL OR r.relation_kind=ANY($4)) "
        f" WHERE w.depth+1 < $3 AND r.{far} IS NOT NULL), "
        "nodes AS (SELECT entity_id, min(depth) AS depth FROM walk GROUP BY entity_id) "
        f"SELECT {_RELATION}, n.depth+1 AS depth FROM nodes n JOIN public.ucm_relations r "
        f"ON r.snapshot_id=$1 AND r.{near}=n.entity_id "
        "AND ($4::text[] IS NULL OR r.relation_kind=ANY($4)) "
        "ORDER BY n.depth, r.entity_id LIMIT $5",
        snapshot_id,
        entity_id,
        depth,
        relation_kinds,
        _limit(limit) + 1,
    )
    return _page(
        snapshot_id, await _relations(conn, snapshot_id, rows[:limit]), rows, limit
    )


async def get_evidence(
    conn: asyncpg.Connection, repository_key: str, relation_id: str
) -> dict:
    """Return one relation with its endpoints, Evidence, Coverage and candidates."""
    snapshot_id = await _snapshot(conn, repository_key)
    rows = await conn.fetch(
        f"SELECT {_RELATION} FROM public.ucm_relations r "
        "WHERE r.snapshot_id=$1 AND r.entity_id=$2",
        snapshot_id,
        relation_id,
    )
    if not rows:
        raise ValueError("relation does not exist in the published snapshot")
    return {
        "snapshot_id": str(snapshot_id),
        **(await _relations(conn, snapshot_id, rows))[0],
    }


def _discovery_scope(keys: list[str] | tuple[str, ...]) -> list[str]:
    if not isinstance(keys, (list, tuple)) or not keys or len(keys) > 32:
        raise ValueError(
            "discovery requires an explicit allowed scope of 1–32 repositories"
        )
    if any(
        not isinstance(k, str) or not k.strip() or "\0" in k or len(k) > 1024
        for k in keys
    ):
        raise ValueError("invalid discovery repository key")
    return sorted(set(keys))


def _discovery_qualifier(kind: str, qualifier: dict | None) -> dict:
    from code_crawler.discovery import KINDS

    if kind not in KINDS:
        raise ValueError("unknown discovery kind")
    value = {} if qualifier is None else qualifier
    fields = {
        "SYMBOL": {"symbol_kind", "parameter_types"},
        "DATABASE": {
            "database_key",
            "version_key",
            "catalog_name",
            "schema_name",
            "object_kind",
            "table_name",
            "column_name",
        },
        "BPMN_PROCESS": {"target_namespace"},
        "HTTP": {"service", "contract_id", "method"},
        "BPMN_WORKER": {"namespace"},
        "REFERENCE_DATA": {"namespace"},
        "KAFKA": {"cluster"},
    }
    if not isinstance(value, dict) or not set(value) <= fields[kind]:
        raise ValueError("invalid discovery qualifier fields")
    required = {
        "DATABASE": {"database_key", "version_key", "catalog_name", "schema_name"},
        "HTTP": {"method"},
        "KAFKA": {"cluster"},
        "REFERENCE_DATA": {"namespace"},
    }
    if not required.get(kind, set()) <= set(value):
        raise ValueError("discovery requires explicit namespace/context qualifiers")
    if kind == "HTTP" and not ({"service", "contract_id"} & set(value)):
        raise ValueError("HTTP discovery requires an explicit service or contract_id")
    for key, item in value.items():
        if key == "parameter_types":
            if (
                not isinstance(item, list)
                or len(item) > 256
                or any(
                    not isinstance(t, str)
                    or not t.strip()
                    or "\0" in t
                    or len(t) > 4096
                    for t in item
                )
            ):
                raise ValueError("invalid ordered parameter_types")
        elif (
            not isinstance(item, str)
            or not item.strip()
            or "\0" in item
            or len(item) > 4096
        ):
            raise ValueError("discovery qualifier values must be nonblank strings")
    if "symbol_kind" in value and value["symbol_kind"] not in (
        "CLASS",
        "METHOD",
        "CONSTRUCTOR",
        "FIELD",
    ):
        raise ValueError("invalid discovery symbol_kind")
    if "object_kind" in value and value["object_kind"] not in (
        "SCHEMA",
        "TABLE",
        "VIEW",
        "MATERIALIZED_VIEW",
        "FOREIGN_TABLE",
        "COLUMN",
    ):
        raise ValueError("invalid database object_kind")
    if "method" in value and value["method"] not in (
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "HEAD",
        "OPTIONS",
        "TRACE",
        "CONNECT",
        "QUERY",
    ):
        raise ValueError("invalid HTTP method")
    return value


async def search_discovery_entries(
    conn: asyncpg.Connection,
    kind: str,
    lookup_key: str,
    *,
    allowed_repository_keys: list[str] | tuple[str, ...],
    repository_keys: list[str] | None = None,
    qualifier: dict | None = None,
    limit: int = 50,
    offset: int = 0,
    expected_fingerprint: str | None = None,
) -> dict:
    """Find potential targets in explicitly allowed current published generations.

    Matches are candidates, including unique matches: no cross-repository relation
    is established. Missing derivative generations are reported as PARTIAL.
    """
    import hashlib
    import json
    import re

    from code_crawler.discovery import SUPPORTED, VERSION

    allowed = _discovery_scope(allowed_repository_keys)
    requested = (
        allowed if repository_keys is None else _discovery_scope(repository_keys)
    )
    if not set(requested) <= set(allowed):
        raise ValueError("discovery repository access denied")
    if (
        not isinstance(lookup_key, str)
        or not lookup_key.strip()
        or len(lookup_key) > 4096
        or "\0" in lookup_key
    ):
        raise ValueError("invalid discovery lookup_key")
    filters = _discovery_qualifier(kind, qualifier)
    _limit(limit)
    if not 0 <= offset <= MAX_OFFSET:
        raise ValueError(f"offset must be between 0 and {MAX_OFFSET}")
    if expected_fingerprint is not None and not re.fullmatch(
        r"[0-9a-f]{64}", expected_fingerprint
    ):
        raise ValueError("invalid discovery fingerprint")
    if offset and expected_fingerprint is None:
        raise ValueError("discovery pagination requires expected_fingerprint")
    payload = await conn.fetchval(
        """
WITH manifest AS MATERIALIZED (
 SELECT requested.repository_key,r.id AS repository_id,p.snapshot_id,
 CASE WHEN s.state='PUBLISHED' AND g.state='READY' AND g.projector_version=$5
 THEN g.generation END AS generation_id
 FROM unnest($1::text[]) requested(repository_key)
 LEFT JOIN public.ucm_repositories r USING(repository_key)
 LEFT JOIN public.ucm_repository_publications p ON p.repository_id=r.id
 LEFT JOIN public.ucm_snapshots s ON s.id=p.snapshot_id
 LEFT JOIN public.search_discovery_generations g ON g.snapshot_id=p.snapshot_id
), matching AS MATERIALIZED (
 SELECT m.repository_key,e.repository_id,e.snapshot_id,e.generation AS generation_id,
 e.entity_id,e.kind,
 CASE WHEN e.kind='DATABASE' THEN COALESCE(e.lookup_key->>6,e.lookup_key->>5,e.lookup_key->>3)
 WHEN e.kind='HTTP' THEN e.lookup_key->>2 ELSE e.lookup_key->>0 END AS lookup_key,e.qualifier,
 e.entity_type,e.source_file_id,e.start_line,e.start_byte_column,e.end_line,e.end_byte_column,e.rule
 FROM manifest m JOIN public.search_discovery_entries e
 ON e.generation=m.generation_id
 WHERE e.kind=$2 AND md5(CASE WHEN e.kind='DATABASE'
 THEN COALESCE(e.lookup_key->>6,e.lookup_key->>5,e.lookup_key->>3) WHEN e.kind='HTTP' THEN e.lookup_key->>2 ELSE e.lookup_key->>0 END)=md5($3)
 AND (CASE WHEN e.kind='DATABASE' THEN COALESCE(e.lookup_key->>6,e.lookup_key->>5,e.lookup_key->>3)
 WHEN e.kind='HTTP' THEN e.lookup_key->>2 ELSE e.lookup_key->>0 END)=$3
 -- JSON containment ignores array order; callable signatures require equality.
 AND NOT EXISTS (SELECT 1 FROM jsonb_each($4::jsonb) f(key,value)
  WHERE e.qualifier -> f.key IS DISTINCT FROM f.value)
 ORDER BY m.repository_key,e.entity_id LIMIT ($6::bigint+$7::bigint)
), page AS (
 SELECT * FROM matching ORDER BY repository_key,entity_id LIMIT $6 OFFSET $7
)
SELECT jsonb_build_object(
 'generation_manifest',(SELECT jsonb_agg(to_jsonb(m) ORDER BY repository_key) FROM manifest m),
 'items',COALESCE((SELECT jsonb_agg(to_jsonb(p) ORDER BY repository_key,entity_id) FROM page p),'[]'::jsonb),
 'match_count_lower_bound',(SELECT count(*) FROM (SELECT 1 FROM matching LIMIT 2) c)
)
""",
        requested,
        kind,
        lookup_key,
        json.dumps(filters),
        VERSION,
        limit + 1,
        offset,
    )
    result = json.loads(payload)
    fingerprint = hashlib.sha256(
        json.dumps(
            [VERSION, result["generation_manifest"]],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if expected_fingerprint is not None and fingerprint != expected_fingerprint:
        raise ValueError("discovery generation changed; restart pagination")
    available = all(
        m["generation_id"] is not None for m in result["generation_manifest"]
    )
    supported = kind in SUPPORTED
    result["fingerprint"] = fingerprint
    result["availability"] = "COMPLETE" if available else "PARTIAL"
    result["coverage"] = {
        "capability": "global.discovery." + kind.lower(),
        "analyzer_version": VERSION,
        "status": ("COMPLETE" if available else "PARTIAL")
        if supported
        else "UNSUPPORTED",
        "reasons": (
            []
            if available
            else ["some allowed repositories lack a current discovery generation"]
        )
        if supported
        else ["no normative UCM target producer for this kind"],
    }
    if kind == "HTTP":
        result["coverage"]["status"] = "PARTIAL"
        result["coverage"]["reasons"].append(
            "OpenAPI contract declarations only; runtime service bindings and callback/webhook targets are unresolved"
        )
    result["resolution"] = (
        "AMBIGUOUS" if result["match_count_lower_bound"] > 1 else "UNRESOLVED"
    )
    result["reason"] = (
        "lookup matches are potential targets; a separate resolver must establish a dependency"
    )
    result["truncated"] = len(result["items"]) > limit
    result["items"] = result["items"][:limit]
    result["next_offset"] = (
        offset + limit if result["truncated"] and offset + limit <= MAX_OFFSET else None
    )
    for item in result["items"]:
        item.update(resolution="UNRESOLVED", certainty="UNKNOWN")
    return result


async def resolve_external_reference(
    conn: asyncpg.Connection,
    source_repository_key: str,
    reference_id: str,
    context: ResolverContext,
    *,
    allowed_repositories: frozenset[str],
    limit: int = 50,
) -> external_candidates.CandidateResolution:
    """Find bounded external declaration candidates in an authorized immutable version context."""
    return await external_candidates.resolve_external_reference(
        conn,
        source_repository_key,
        reference_id,
        context,
        allowed_repositories=allowed_repositories,
        limit=limit,
    )
