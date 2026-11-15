"""Versioned candidate-only projections over immutable canonical publications."""

import json
from uuid import NAMESPACE_URL, UUID, uuid5

import asyncpg

VERSION = "discovery/2"
MAX_REPOSITORIES = 32
MAX_LIMIT = 200
COVERAGE = {
    "SYMBOL": "PARTIAL",
    "SYMBOL_SIGNATURE": "PARTIAL",
    "DATABASE": "PARTIAL",
    "BPMN_PROCESS": "PARTIAL",
    "HTTP": "PARTIAL",
    "BPMN_WORKER": "UNSUPPORTED",
    "KAFKA_TOPIC": "UNSUPPORTED",
    "DATASET": "UNSUPPORTED",
    "KAFKA": "UNSUPPORTED",
    "REFERENCE_DATA": "UNSUPPORTED",
}


KINDS = (
    "SYMBOL",
    "DATABASE",
    "BPMN_PROCESS",
    "HTTP",
    "BPMN_WORKER",
    "REFERENCE_DATA",
    "KAFKA",
)
SUPPORTED = ("SYMBOL", "DATABASE", "BPMN_PROCESS", "HTTP")


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
        "SELECT generation,projector_version FROM public.search_discovery_generations WHERE snapshot_id=$1 AND state='READY'",
        snapshot_id,
    )
    if (
        existing
        and existing["generation"] == generation
        and existing["projector_version"] == VERSION
    ):
        return generation
    await conn.execute("SELECT set_config('code_crawler.discovery_build','on',true)")
    await conn.execute(
        "DELETE FROM public.search_discovery_generations WHERE snapshot_id=$1",
        snapshot_id,
    )
    await conn.execute(
        "INSERT INTO public.search_discovery_generations(snapshot_id,repository_id,generation,projector_version,coverage,state) VALUES($1,$2,$3,$4,$5::jsonb,'BUILDING')",
        snapshot_id,
        snapshot["repository_id"],
        generation,
        VERSION,
        json.dumps(COVERAGE),
    )
    # Known callable arity is represented even when it is zero; classes have no signature row.
    projection_sql = """
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
                                   'schema_fingerprint',d.schema_fingerprint,'catalog_name',d.catalog_name,
                                   'schema_name',d.schema_name,'object_kind',d.object_kind,
                                   'table_name',d.table_name,'column_name',d.column_name)
          FROM public.ucm_database_objects d WHERE d.snapshot_id=$1
          UNION ALL
          SELECT s.entity_id,'BPMN_PROCESS',jsonb_build_array(v.literal #>> '{}'),
                 jsonb_build_object('namespace','http://www.omg.org/spec/BPMN/20100524/MODEL',
                                    'target_namespace',namespace.literal #>> '{}')
          FROM public.ucm_symbols s
          JOIN public.ucm_entities e USING(snapshot_id,entity_id)
          JOIN public.ucm_relations r ON r.snapshot_id=s.snapshot_id AND r.source_id=s.entity_id
           AND r.relation_kind='BPMN_ATTRIBUTE' AND r.resolution='RESOLVED'
          JOIN public.ucm_entities a ON a.snapshot_id=r.snapshot_id AND a.entity_id=r.target_id AND a.name='id'
          JOIN public.ucm_values v ON v.snapshot_id=a.snapshot_id AND v.entity_id=a.entity_id
          LEFT JOIN LATERAL (
           SELECT nv.literal FROM public.ucm_symbols root
           JOIN public.ucm_entities re USING(snapshot_id,entity_id)
           JOIN public.ucm_relations nr ON nr.snapshot_id=root.snapshot_id AND nr.source_id=root.entity_id
            AND nr.relation_kind='BPMN_ATTRIBUTE' AND nr.resolution='RESOLVED'
           JOIN public.ucm_entities na ON na.snapshot_id=nr.snapshot_id AND na.entity_id=nr.target_id AND na.name='targetNamespace'
           JOIN public.ucm_values nv ON nv.snapshot_id=na.snapshot_id AND nv.entity_id=na.entity_id
           WHERE root.snapshot_id=s.snapshot_id AND re.source_file_id=e.source_file_id
           AND root.symbol_kind='BPMN_ELEMENT'
           AND root.qualified_name='{http://www.omg.org/spec/BPMN/20100524/MODEL}definitions'
           AND nv.value_kind='LITERAL' AND jsonb_typeof(nv.literal)='string'
          ) namespace ON true
          WHERE s.snapshot_id=$1 AND s.symbol_kind='BPMN_ELEMENT'
          AND s.qualified_name='{http://www.omg.org/spec/BPMN/20100524/MODEL}process'
          AND v.value_kind='LITERAL' AND jsonb_typeof(v.literal)='string' AND length(v.literal #>> '{}')>0

          UNION ALL
          SELECT op.entity_id,'HTTP',jsonb_build_array(NULL,mv.literal #>> '{}',pv.literal #>> '{}',root.entity_id),
                 jsonb_build_object('service',NULL,'contract_id',root.entity_id,
                                    'method',mv.literal #>> '{}','path',pv.literal #>> '{}')
          FROM public.ucm_symbols root
          JOIN public.ucm_relations rp ON rp.snapshot_id=root.snapshot_id AND rp.source_id=root.entity_id
            AND rp.relation_kind='CONTAINS' AND rp.resolution='RESOLVED'
          JOIN public.ucm_entities paths ON paths.snapshot_id=rp.snapshot_id AND paths.entity_id=rp.target_id AND paths.name='paths'
          JOIN public.ucm_relations ri ON ri.snapshot_id=paths.snapshot_id AND ri.source_id=paths.entity_id
            AND ri.relation_kind='CONTAINS' AND ri.resolution='RESOLVED'
          JOIN public.ucm_relations ro ON ro.snapshot_id=ri.snapshot_id AND ro.source_id=ri.target_id
            AND ro.relation_kind='CONTAINS' AND ro.resolution='RESOLVED'
          JOIN public.ucm_symbols op ON op.snapshot_id=ro.snapshot_id AND op.entity_id=ro.target_id AND op.symbol_kind='OPENAPI_OPERATION'
          JOIN public.ucm_relations mr ON mr.snapshot_id=op.snapshot_id AND mr.source_id=op.entity_id
            AND mr.relation_kind='OPENAPI_ATTRIBUTE' AND mr.resolution='RESOLVED'
          JOIN public.ucm_entities ma ON ma.snapshot_id=mr.snapshot_id AND ma.entity_id=mr.target_id AND ma.name='method'
          JOIN public.ucm_values mv ON mv.snapshot_id=ma.snapshot_id AND mv.entity_id=ma.entity_id AND mv.value_kind='LITERAL'
          JOIN public.ucm_relations pr ON pr.snapshot_id=op.snapshot_id AND pr.source_id=op.entity_id
            AND pr.relation_kind='OPENAPI_ATTRIBUTE' AND pr.resolution='RESOLVED'
          JOIN public.ucm_entities pa ON pa.snapshot_id=pr.snapshot_id AND pa.entity_id=pr.target_id AND pa.name='path'
          JOIN public.ucm_values pv ON pv.snapshot_id=pa.snapshot_id AND pv.entity_id=pa.entity_id AND pv.value_kind='LITERAL'
          WHERE root.snapshot_id=$1 AND root.symbol_kind='OPENAPI_DOCUMENT'
            AND mv.literal #>> '{}' IN ('GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS','TRACE','CONNECT','QUERY')
            AND pv.literal #>> '{}' LIKE '/%' AND pv.literal #>> '{}' !~ '[?#]'
        )
        INSERT INTO public.search_discovery_entries
        SELECT e.snapshot_id,$2,e.repository_id,e.entity_id,e.entity_type,p.kind,p.key,p.qualifier,
               e.source_file_id,e.start_line,e.start_byte_column,e.end_line,e.end_byte_column,'canonical.declaration/1'
        FROM projections p JOIN public.ucm_entities e ON e.snapshot_id=$1 AND e.entity_id=p.entity_id
    """
    # Fresh snapshot IDs are absent from statistics; a custom multi-join plan can
    # underestimate them catastrophically. Keep this choice local to the projection.
    async with conn.transaction():
        plan_mode = await conn.fetchval("SHOW plan_cache_mode")
        await conn.execute(
            "SELECT set_config('plan_cache_mode','force_generic_plan',true)"
        )
        await conn.execute(projection_sql, snapshot_id, generation)
        await conn.execute("SELECT set_config('plan_cache_mode',$1,true)", plan_mode)

    await conn.execute(
        "UPDATE public.search_discovery_generations SET state='READY' WHERE generation=$1",
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
        "WHERE r.repository_key=ANY($1) AND g.projector_version=$2 AND g.state='READY'",
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
          AND g.projector_version=$4 AND g.state='READY'
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
