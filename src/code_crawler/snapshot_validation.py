"""Snapshot-wide SQL invariants without hydrating snapshot-wide Python models."""

from uuid import UUID, uuid4

import asyncpg


async def check_global_invariants(conn: asyncpg.Connection, snapshot_id: UUID) -> None:
    """Check global uniqueness using the same keys as UcmBatch."""
    for table, where, keys, message in (
        ("ucm_source_files", "true", "path", "duplicate source file path"),
        (
            "ucm_operation_values",
            "direction='OUTPUT'",
            "value_id",
            "value has multiple producers",
        ),
        (
            "ucm_source_analyses",
            "true",
            "source_file_id",
            "source file cannot have multiple adapter analysis reports",
        ),
        (
            "ucm_sql_variants",
            "true",
            "candidate_id",
            "SQL candidate has multiple construction owners",
        ),
        (
            "ucm_sql_statements",
            "true",
            "candidate_id,statement_index",
            "duplicate SQL statement position",
        ),
        (
            "ucm_sql_placeholders",
            "true",
            "statement_id,ordinal",
            "duplicate SQL placeholder ordinal",
        ),
        (
            "ucm_relations",
            "relation_kind='USES_SQL_CONSTRUCTION'",
            "source_id",
            "SQL execution must have one construction descriptor",
        ),
    ):
        if await conn.fetchval(
            f"SELECT EXISTS(SELECT 1 FROM {table} WHERE snapshot_id=$1 AND {where} "
            f"GROUP BY {keys} HAVING count(*)>1)",
            snapshot_id,
        ):
            raise ValueError(message)


async def check_scope_graph(conn: asyncpg.Connection, snapshot_id: UUID) -> None:
    """Double parent pointers: acyclic paths reach NULL within log2(N)+1 rounds.

    PostgreSQL owns the working set, governed by work_mem/temp storage. No path
    arrays or all-scope dictionaries are built in the Python validator.
    """
    count = await conn.fetchval(
        "SELECT count(*) FROM ucm_scopes WHERE snapshot_id=$1", snapshot_id
    )
    if not count:
        return
    name = "validation_scopes_" + uuid4().hex
    await conn.execute(
        f"CREATE TEMP TABLE {name} (id text PRIMARY KEY,parent_id text) ON COMMIT DROP"
    )
    await conn.execute(
        f"INSERT INTO pg_temp.{name} SELECT entity_id,parent_scope_id FROM ucm_scopes WHERE snapshot_id=$1",
        snapshot_id,
    )
    await conn.execute(f"ANALYZE pg_temp.{name}")
    for _ in range(count.bit_length()):
        await conn.execute(
            f"UPDATE pg_temp.{name} s SET parent_id=p.parent_id FROM pg_temp.{name} p WHERE s.parent_id=p.id AND s.parent_id IS DISTINCT FROM p.parent_id"
        )
        if not await conn.fetchval(
            f"SELECT EXISTS(SELECT 1 FROM pg_temp.{name} WHERE parent_id IS NOT NULL)"
        ):
            return
    raise ValueError("cyclic parent_scope references")


async def check_sql_semantics(conn: asyncpg.Connection, snapshot_id: UUID) -> None:
    """SQL counterpart of ingestion.check_semantics; all queries are snapshot-scoped."""
    # Normalize both resolved targets and candidate references once. The projection
    # is temporary, contains no source text, and cannot modify canonical facts.
    name = "validation_links_" + uuid4().hex
    await conn.execute(
        f"""CREATE TEMP TABLE {name} ON COMMIT DROP AS
        SELECT r.entity_id AS relation_id,r.relation_kind,r.source_id,r.resolution,r.target_id
        FROM ucm_relations r WHERE r.snapshot_id=$1 AND r.target_id IS NOT NULL
          AND r.relation_kind IN ('USES_SQL_CONSTRUCTION','EXECUTES_STATEMENT','BINDS_PARAMETER','USES_DATABASE_CONTEXT')
        UNION ALL
        SELECT r.entity_id,r.relation_kind,r.source_id,r.resolution,c.candidate_id
        FROM ucm_relations r JOIN ucm_relation_candidates c
          ON c.snapshot_id=r.snapshot_id AND c.relation_id=r.entity_id
        WHERE r.snapshot_id=$1
          AND r.relation_kind IN ('USES_SQL_CONSTRUCTION','EXECUTES_STATEMENT','BINDS_PARAMETER','USES_DATABASE_CONTEXT')""",
        snapshot_id,
    )
    await conn.execute(
        f"CREATE INDEX ON pg_temp.{name}(source_id,relation_kind,target_id)"
    )
    await conn.execute(f"ANALYZE pg_temp.{name}")
    checks = (
        (
            "SQL statement text must match candidate slice",
            """
            SELECT 1 FROM ucm_sql_statements s LEFT JOIN ucm_sql_variants v
            ON v.snapshot_id=s.snapshot_id AND v.candidate_id=s.candidate_id
            WHERE s.snapshot_id=$1 AND (v.candidate_id IS NULL OR
                substring(v.text FROM s.text_start+1 FOR s.text_end-s.text_start) COLLATE "C"<>s.text COLLATE "C")""",
        ),
        (
            "partial SQL construction cannot assert complete semantics",
            """
            SELECT 1 FROM ucm_sql_statements s JOIN ucm_sql_variants v
            ON v.snapshot_id=s.snapshot_id AND v.candidate_id=s.candidate_id
            WHERE s.snapshot_id=$1 AND v.partial AND s.parse_status<>'PARTIAL'""",
        ),
        (
            "partial SQL construction cannot assert accesses",
            """
            SELECT 1 FROM ucm_data_accesses a JOIN ucm_sql_statements s
            ON s.snapshot_id=a.snapshot_id AND s.entity_id=a.statement_id
            JOIN ucm_sql_variants v ON v.snapshot_id=s.snapshot_id AND v.candidate_id=s.candidate_id
            WHERE a.snapshot_id=$1 AND v.partial""",
        ),
        (
            "execution statement must originate in its SQL construction",
            f"""
            SELECT 1 FROM pg_temp.{name} e JOIN ucm_sql_statements s
            ON s.snapshot_id=$1 AND s.entity_id=e.target_id
            WHERE e.relation_kind='EXECUTES_STATEMENT' AND NOT EXISTS (
                SELECT 1 FROM pg_temp.{name} u JOIN ucm_sql_variants v
                ON v.snapshot_id=$1 AND v.construction_id=u.target_id
                WHERE u.source_id=e.source_id AND u.relation_kind='USES_SQL_CONSTRUCTION'
                  AND v.candidate_id=s.candidate_id)""",
        ),
        (
            "definite execution statement requires complete unambiguous origin",
            f"""
            SELECT 1 FROM pg_temp.{name} e JOIN ucm_sql_statements s
            ON s.snapshot_id=$1 AND s.entity_id=e.target_id
            WHERE e.relation_kind='EXECUTES_STATEMENT' AND e.resolution='RESOLVED'
              AND (s.parse_status<>'COMPLETE' OR NOT EXISTS (
                SELECT 1 FROM ucm_relations u WHERE u.snapshot_id=$1
                AND u.source_id=e.source_id AND u.relation_kind='USES_SQL_CONSTRUCTION'
                AND u.resolution='RESOLVED') OR (SELECT count(DISTINCT v.candidate_id)
                FROM pg_temp.{name} u JOIN ucm_sql_variants v
                ON v.snapshot_id=$1 AND v.construction_id=u.target_id
                WHERE u.source_id=e.source_id AND u.relation_kind='USES_SQL_CONSTRUCTION')<>1)""",
        ),
        (
            "binding placeholder must belong to an execution statement",
            f"""
            SELECT 1 FROM pg_temp.{name} e JOIN ucm_sql_bindings b
            ON b.snapshot_id=$1 AND b.entity_id=e.source_id
            JOIN ucm_sql_placeholders p ON p.snapshot_id=$1 AND p.entity_id=e.target_id
            WHERE e.relation_kind='BINDS_PARAMETER' AND NOT EXISTS (
                SELECT 1 FROM pg_temp.{name} x WHERE x.source_id=b.execution_id
                AND x.relation_kind='EXECUTES_STATEMENT' AND x.target_id=p.statement_id)""",
        ),
        (
            "binding position must match the SQL placeholder",
            f"""
            SELECT 1 FROM pg_temp.{name} e JOIN ucm_sql_bindings b
            ON b.snapshot_id=$1 AND b.entity_id=e.source_id
            JOIN ucm_sql_placeholders p ON p.snapshot_id=$1 AND p.entity_id=e.target_id
            WHERE e.relation_kind='BINDS_PARAMETER' AND b.binding_kind='POSITIONAL'
              AND (p.parameter_kind<>'POSITIONAL' OR b.position IS DISTINCT FROM p.position)""",
        ),
        (
            "binding name must match the SQL placeholder",
            f"""
            SELECT 1 FROM pg_temp.{name} e JOIN ucm_sql_bindings b
            ON b.snapshot_id=$1 AND b.entity_id=e.source_id
            JOIN ucm_sql_placeholders p ON p.snapshot_id=$1 AND p.entity_id=e.target_id
            WHERE e.relation_kind='BINDS_PARAMETER' AND b.binding_kind='NAMED'
              AND (p.parameter_kind<>'NAMED' OR b.parameter_name COLLATE "C" IS DISTINCT FROM p.parameter_name COLLATE "C")""",
        ),
        (
            "incomplete SQL binding cannot assert definite parameter link",
            f"""
            SELECT 1 FROM pg_temp.{name} e JOIN ucm_sql_bindings b
            ON b.snapshot_id=$1 AND b.entity_id=e.source_id
            WHERE e.relation_kind='BINDS_PARAMETER' AND e.resolution='RESOLVED' AND b.status<>'BOUND'""",
        ),
        (
            "contextual database access must belong to an execution statement",
            f"""
            SELECT 1 FROM ucm_database_accesses d JOIN ucm_data_accesses a
            ON a.snapshot_id=d.snapshot_id AND a.entity_id=d.access_id
            WHERE d.snapshot_id=$1 AND d.execution_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM pg_temp.{name} e WHERE e.source_id=d.execution_id
                AND e.relation_kind='EXECUTES_STATEMENT' AND e.target_id=a.statement_id)""",
        ),
        (
            "contextual database access must use an execution context",
            f"""
            SELECT 1 FROM ucm_database_accesses d WHERE d.snapshot_id=$1
            AND d.execution_id IS NOT NULL AND d.context_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM pg_temp.{name} e WHERE e.source_id=d.execution_id
                AND e.relation_kind='USES_DATABASE_CONTEXT' AND e.target_id=d.context_id)""",
        ),
    )
    for message, sql in checks:
        if await conn.fetchval("SELECT EXISTS(" + sql + ")", snapshot_id):
            raise ValueError(message)
