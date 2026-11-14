"""Persistent ingest job state, safe retry and snapshot garbage collection."""

import json
from uuid import UUID, uuid4

import asyncpg

# Первый ключ пары advisory-блокировки; второй — hashtext(id задания).
_JOB_LOCK = 4_217_002
_LOCK = "SELECT pg_try_advisory_lock($1, hashtext($2::text))"
_UNLOCK = "SELECT pg_advisory_unlock($1, hashtext($2::text))"


# Only snapshot-owned tables; new migrations must update this registry.
# Search generations go first: cascading deletion removes their sealed documents.
# Otherwise alphabetical order keeps source links ahead of source files (immediate FK).
_SNAPSHOT_TABLES = (
    "ingest_file_dependencies",
    "ingest_file_entities",
    "ingest_legacy_edges",
    "ingest_legacy_nodes",
    "ingest_legacy_refs",
    "ingest_legacy_snapshots",
    "ingest_snapshot_adapters",
    "ingest_snapshot_profiles",
    "search_index_generations",
    "search_documents",
    "search_index_publications",
    "ucm_coverage_reasons",
    "ucm_data_accesses",
    "ucm_database_accesses",
    "ucm_database_contexts",
    "ucm_database_objects",
    "ucm_database_search_paths",
    "ucm_entities",
    "ucm_evidence",
    "ucm_external_references",
    "ucm_occurrences",
    "ucm_operation_values",
    "ucm_operations",
    "ucm_orm_mapping_names",
    "ucm_orm_mappings",
    "ucm_orm_operations",
    "ucm_orm_queries",
    "ucm_orm_reasons",
    "ucm_relation_candidates",
    "ucm_relations",
    "ucm_scopes",
    "ucm_snapshot_sources",
    "ucm_snapshot_validations",
    "ucm_source_analyses",
    "ucm_source_analysis_capabilities",
    "ucm_source_analysis_reasons",
    "ucm_source_diagnostics",
    "ucm_source_evidence_legacy_snapshots",
    "ucm_source_files",
    "ucm_sql_access_names",
    "ucm_sql_binding_reasons",
    "ucm_sql_bindings",
    "ucm_sql_constructions",
    "ucm_sql_executions",
    "ucm_sql_fragments",
    "ucm_sql_partial_reasons",
    "ucm_sql_placeholders",
    "ucm_sql_statement_reasons",
    "ucm_sql_statements",
    "ucm_sql_variants",
    "ucm_symbols",
    "ucm_type_refs",
    "ucm_values",
)


async def begin(
    conn: asyncpg.Connection, repository_id: UUID, parameters: dict
) -> UUID:
    """Record a RUNNING job owned by this session until the connection closes."""
    job_id = uuid4()
    # Блокировка сессионная: упавший процесс теряет её сам, и задание можно повторить.
    await conn.fetchval(_LOCK, _JOB_LOCK, str(job_id))
    await conn.execute(
        "INSERT INTO public.ingest_jobs(id,repository_id,parameters) VALUES ($1,$2,$3)",
        job_id,
        repository_id,
        json.dumps(parameters),
    )
    return job_id


async def claim(conn: asyncpg.Connection, job_id: UUID) -> dict:
    """Start the next attempt of a failed or abandoned job; return its parameters."""
    if not await conn.fetchval(_LOCK, _JOB_LOCK, str(job_id)):
        raise ValueError("ingest job is running in another process")
    parameters = await conn.fetchval(
        "UPDATE public.ingest_jobs SET state='RUNNING', stage='INDEX', snapshot_id=NULL, "
        "attempt=attempt+1, failure=NULL, updated_at=now() "
        "WHERE id=$1 AND state<>'SUCCEEDED' RETURNING parameters",
        job_id,
    )
    if parameters is None:
        await conn.fetchval(_UNLOCK, _JOB_LOCK, str(job_id))
        raise ValueError("ingest job does not exist or has already succeeded")
    return json.loads(parameters)


async def advance(
    conn: asyncpg.Connection, job_id: UUID, stage: str, snapshot_id: UUID
) -> None:
    await conn.execute(
        "UPDATE public.ingest_jobs SET stage=$2, snapshot_id=$3, updated_at=now() WHERE id=$1",
        job_id,
        stage,
        snapshot_id,
    )


async def finish(
    conn: asyncpg.Connection, job_id: UUID, error: Exception | None = None
) -> None:
    """Close the job as SUCCEEDED, or FAILED with structured failure diagnostics."""
    failure = None
    if error is not None:
        failure = {"type": type(error).__name__, "message": str(error)}
        for name in ("adapter_key", "stage"):
            if hasattr(error, name):
                failure[name] = getattr(error, name)
        if hasattr(error, "issues"):
            failure["issues"] = [
                {"path": issue.path, **issue.diagnostic.model_dump(mode="json")}
                for issue in error.issues
            ]
    await conn.execute(
        "UPDATE public.ingest_jobs SET state=$2, failure=$3, updated_at=now() WHERE id=$1",
        job_id,
        "FAILED" if error is not None else "SUCCEEDED",
        json.dumps(failure) if failure else None,
    )
    await conn.fetchval(_UNLOCK, _JOB_LOCK, str(job_id))


async def reap(conn: asyncpg.Connection) -> list[UUID]:
    """Mark RUNNING jobs whose owning process is gone as FAILED."""
    reaped = []
    for row in await conn.fetch(
        "SELECT id FROM public.ingest_jobs WHERE state='RUNNING'"
    ):
        if await conn.fetchval(_LOCK, _JOB_LOCK, str(row["id"])):
            await finish(
                conn, row["id"], RuntimeError("process ended without reporting")
            )
            reaped.append(row["id"])
    return reaped


async def _delete_snapshots(conn: asyncpg.Connection, ids: list[UUID]) -> None:
    # shortcut: row-by-row guarded deletes, slow on huge snapshots; partition by
    # snapshot and drop partitions when GC time starts to matter.
    # The benchmark also runs GC against historical migration prefixes.
    existing = {
        row["name"]
        for row in await conn.fetch(
            "SELECT name FROM unnest($1::text[]) AS t(name) "
            "WHERE to_regclass('public.' || name) IS NOT NULL",
            list(_SNAPSHOT_TABLES),
        )
    }
    for table in _SNAPSHOT_TABLES:
        if table not in existing:
            continue
        await conn.execute(f"DELETE FROM public.{table} WHERE snapshot_id=ANY($1)", ids)
    await conn.execute("DELETE FROM public.ucm_snapshots WHERE id=ANY($1)", ids)


async def collect_garbage(
    conn: asyncpg.Connection,
    *,
    building_older_than_hours: float | None = None,
    keep_retired: int | None = None,
) -> dict[str, list[UUID]]:
    """Delete abandoned BUILDING snapshots and RETIRED ones beyond the kept count.

    PUBLISHED, READY and VALIDATING snapshots are never touched.
    """
    result: dict[str, list[UUID]] = {"reaped_jobs": await reap(conn)}
    async with conn.transaction():
        await conn.execute("SET CONSTRAINTS ALL DEFERRED")
        await conn.execute("SET LOCAL code_crawler.gc = 'on'")
        building = []
        if building_older_than_hours is not None:
            if building_older_than_hours < 0:
                raise ValueError("building age must not be negative")
            # FOR UPDATE: параллельная validation не успеет увести snapshot из BUILDING.
            building = [
                r["id"]
                for r in await conn.fetch(
                    "SELECT s.id FROM public.ucm_snapshots s WHERE s.state='BUILDING' "
                    "AND s.created_at <= now() - make_interval(secs => $1) "
                    "AND NOT EXISTS (SELECT 1 FROM public.ingest_jobs j WHERE "
                    "j.repository_id=s.repository_id AND j.state='RUNNING') FOR UPDATE",
                    building_older_than_hours * 3600,
                )
            ]
        retired = []
        if keep_retired is not None:
            if keep_retired < 0:
                raise ValueError("kept RETIRED count must not be negative")
            retired = [
                r["id"]
                for r in await conn.fetch(
                    "SELECT id FROM public.ucm_snapshots WHERE id IN (SELECT id FROM ("
                    "SELECT id, row_number() OVER (PARTITION BY repository_id "
                    "ORDER BY created_at DESC, id) AS position FROM public.ucm_snapshots "
                    "WHERE state='RETIRED') ranked WHERE position > $1) FOR UPDATE",
                    keep_retired,
                )
            ]
        if building or retired:
            await _delete_snapshots(conn, building + retired)
    result["building"] = building
    result["retired"] = retired
    return result
