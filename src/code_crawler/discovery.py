"""Versioned candidate-only projections over immutable canonical publications."""

import json
from uuid import NAMESPACE_URL, UUID, uuid5

import asyncpg

VERSION = "discovery/1"
MAX_REPOSITORIES = 32
MAX_LIMIT = 200
COVERAGE = {
    "SYMBOL": "PARTIAL",
    "SYMBOL_SIGNATURE": "PARTIAL",
    "DATABASE": "PARTIAL",
    "BPMN_PROCESS": "PARTIAL",
    "HTTP": "UNSUPPORTED",
    "BPMN_WORKER": "UNSUPPORTED",
    "KAFKA_TOPIC": "UNSUPPORTED",
    "DATASET": "UNSUPPORTED",
}


async def build_generation(conn: asyncpg.Connection, snapshot_id: UUID) -> UUID:
    """Build a publication's generation in the caller's atomic write transaction."""
    if not conn.is_in_transaction():
        raise ValueError("discovery build requires a publication transaction")
    snapshot = await conn.fetchrow(
        "SELECT repository_id,state FROM public.ucm_snapshots WHERE id=$1 FOR UPDATE",
        snapshot_id,
    )
    if snapshot is None or snapshot["state"] != "PUBLISHED":
        raise ValueError("discovery requires a published snapshot")
    generation = uuid5(NAMESPACE_URL, f"{VERSION}:{snapshot_id}")
    existing = await conn.fetchrow(
        "SELECT generation,projector_version FROM public.search_discovery_generations WHERE snapshot_id=$1",
        snapshot_id,
    )
    if (
        existing
        and existing["generation"] == generation
        and existing["projector_version"] == VERSION
    ):
        return generation
    await conn.execute(
        "DELETE FROM public.search_discovery_generations WHERE snapshot_id=$1",
        snapshot_id,
    )
    await conn.execute(
        "INSERT INTO public.search_discovery_generations VALUES($1,$2,$3,$4,$5::jsonb)",
        snapshot_id,
        snapshot["repository_id"],
        generation,
        VERSION,
        json.dumps(COVERAGE),
    )
    # Known callable arity is represented even when it is zero; classes have no signature row.
    await conn.execute(
        """
        WITH symbols AS (
          SELECT s.*,COALESCE((SELECT jsonb_agg(t.name ORDER BY t.position)
              FROM public.ucm_type_refs t WHERE t.snapshot_id=s.snapshot_id
              AND t.owner_id=s.entity_id AND t.role='PARAMETER'),'[]'::jsonb) AS parameters
          FROM public.ucm_symbols s WHERE s.snapshot_id=$1
            AND s.symbol_kind IN ('CLASS','METHOD','CONSTRUCTOR','FIELD')
        ), projections AS (
          SELECT s.entity_id,'SYMBOL' AS kind,jsonb_build_array(s.qualified_name) AS key,
                 jsonb_build_object('symbol_kind',s.symbol_kind,'qualified_name',s.qualified_name,
                                    'parameter_types',CASE WHEN s.owner_key IS NOT NULL THEN s.parameters END) AS qualifier
          FROM symbols s
          UNION ALL
          SELECT s.entity_id,'SYMBOL_SIGNATURE',jsonb_build_array(s.qualified_name,s.parameters),
                 jsonb_build_object('symbol_kind',s.symbol_kind,'qualified_name',s.qualified_name,'parameter_types',s.parameters)
          FROM symbols s WHERE s.owner_key IS NOT NULL
          UNION ALL
          SELECT d.entity_id,'DATABASE',jsonb_build_array(d.database_key,d.version_key,d.catalog_name,
                 d.schema_name,d.object_kind,d.table_name,d.column_name),
                 jsonb_build_object('database_key',d.database_key,'version_key',d.version_key,
                                   'schema_fingerprint',d.schema_fingerprint)
          FROM public.ucm_database_objects d WHERE d.snapshot_id=$1
          UNION ALL
          SELECT s.entity_id,'BPMN_PROCESS',jsonb_build_array(v.literal #>> '{}'),
                 jsonb_build_object('namespace','http://www.omg.org/spec/BPMN/20100524/MODEL')
          FROM public.ucm_symbols s
          JOIN public.ucm_relations r ON r.snapshot_id=s.snapshot_id AND r.source_id=s.entity_id
            AND r.relation_kind='BPMN_ATTRIBUTE' AND r.resolution='RESOLVED'
          JOIN public.ucm_entities attr ON attr.snapshot_id=r.snapshot_id AND attr.entity_id=r.target_id AND attr.name='id'
          JOIN public.ucm_values v ON v.snapshot_id=attr.snapshot_id AND v.entity_id=attr.entity_id
          WHERE s.snapshot_id=$1 AND s.symbol_kind='BPMN_ELEMENT'
            AND s.qualified_name='{http://www.omg.org/spec/BPMN/20100524/MODEL}process'
            AND v.value_kind='LITERAL' AND jsonb_typeof(v.literal)='string'
        )
        INSERT INTO public.search_discovery_entries
        SELECT e.snapshot_id,$2,e.repository_id,e.entity_id,e.entity_type,p.kind,p.key,p.qualifier,
               e.source_file_id,e.start_line,e.start_byte_column,e.end_line,e.end_byte_column,'canonical.declaration/1'
        FROM projections p JOIN public.ucm_entities e ON e.snapshot_id=$1 AND e.entity_id=p.entity_id
        """,
        snapshot_id,
        generation,
    )
    return generation


async def refresh_discovery(conn: asyncpg.Connection, repository_key: str) -> UUID:
    """Backfill/refresh one current publication without touching other repositories."""
    if conn.is_in_transaction():
        raise ValueError("refresh requires a free connection")
    async with conn.transaction():
        row = await conn.fetchrow(
            "SELECT p.snapshot_id FROM public.ucm_repositories r JOIN public.ucm_repository_publications p "
            "ON p.repository_id=r.id WHERE r.repository_key=$1 FOR UPDATE OF r",
            repository_key,
        )
        if row is None:
            raise ValueError("repository has no published snapshot")
        return await build_generation(conn, row["snapshot_id"])


def authorize(
    repository_keys: tuple[str, ...], allowed_repositories: frozenset[str]
) -> None:
    """Require explicit grants before resolving identifiers or reading any facts."""
    if (
        not repository_keys
        or len(repository_keys) > MAX_REPOSITORIES
        or len(set(repository_keys)) != len(repository_keys)
        or any(not isinstance(k, str) or not k.strip() for k in repository_keys)
    ):
        raise ValueError("invalid repository selection")
    if not allowed_repositories or not set(repository_keys) <= allowed_repositories:
        raise PermissionError("repository access denied")


async def _lookup(
    conn: asyncpg.Connection,
    kind: str,
    key: tuple,
    *,
    repository_keys: tuple[str, ...],
    allowed_repositories: frozenset[str],
    limit: int = 50,
) -> dict:
    """Find bounded candidates from current publications within explicit trusted grants."""
    authorize(repository_keys, allowed_repositories)
    if (
        kind not in COVERAGE
        or isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MAX_LIMIT
    ):
        raise ValueError("invalid discovery kind/limit")
    available = await conn.fetch(
        "SELECT r.repository_key FROM public.ucm_repositories r "
        "JOIN public.ucm_repository_publications p ON p.repository_id=r.id "
        "JOIN public.search_discovery_generations g ON g.snapshot_id=p.snapshot_id "
        "WHERE r.repository_key=ANY($1) AND g.projector_version=$2",
        list(repository_keys),
        VERSION,
    )
    unavailable = sorted(
        set(repository_keys) - {r["repository_key"] for r in available}
    )
    rows = await conn.fetch(
        """
        SELECT e.*,r.repository_key FROM public.search_discovery_entries e
        JOIN public.ucm_repositories r ON r.id=e.repository_id
        JOIN public.ucm_repository_publications p ON p.repository_id=e.repository_id AND p.snapshot_id=e.snapshot_id
        JOIN public.search_discovery_generations g ON g.snapshot_id=e.snapshot_id AND g.generation=e.generation
        WHERE r.repository_key=ANY($1) AND e.kind=$2
          AND md5(e.lookup_key::text)=md5($3::jsonb::text) AND e.lookup_key=$3::jsonb
          AND g.projector_version=$4
        ORDER BY r.repository_key,e.snapshot_id,e.entity_id LIMIT $5
        """,
        list(repository_keys),
        kind,
        json.dumps(key, ensure_ascii=False),
        VERSION,
        limit + 1,
    )
    return {
        "items": [
            {
                **dict(r),
                "lookup_key": json.loads(r["lookup_key"]),
                "qualifier": json.loads(r["qualifier"]),
            }
            for r in rows[:limit]
        ],
        "unavailable_repositories": unavailable,
        "truncated": len(rows) > limit,
        "coverage": COVERAGE[kind],
        "resolution": "UNRESOLVED",
    }


async def lookup(
    conn: asyncpg.Connection,
    kind: str,
    key: tuple,
    *,
    repository_keys: tuple[str, ...],
    allowed_repositories: frozenset[str],
    limit: int = 50,
) -> dict:
    """Read candidates in one consistent generation; absent grants always deny access."""
    authorize(repository_keys, allowed_repositories)
    if conn.is_in_transaction():
        if (
            await conn.fetchval("SHOW transaction_isolation")
            not in ("repeatable read", "serializable")
            or await conn.fetchval("SHOW transaction_read_only") != "on"
        ):
            raise ValueError(
                "discovery requires a read-only repeatable-read transaction"
            )
        return await _lookup(
            conn,
            kind,
            key,
            repository_keys=repository_keys,
            allowed_repositories=allowed_repositories,
            limit=limit,
        )
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        return await _lookup(
            conn,
            kind,
            key,
            repository_keys=repository_keys,
            allowed_repositories=allowed_repositories,
            limit=limit,
        )
