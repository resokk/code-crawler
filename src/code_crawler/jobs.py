"""Persistent ingest job state, safe retry and snapshot garbage collection."""

import json
import math
from typing import TypedDict
from uuid import UUID, uuid4

import asyncpg

from code_crawler import db, snapshots

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
    "search_index_publications",
    "search_index_generations",
    "search_documents",
    "search_discovery_entries",
    "search_discovery_generations",
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
    """Reap abandoned jobs transactionally; leases release even after cancellation."""
    reaped = []
    async with conn.transaction():
        for row in await conn.fetch(
            "SELECT j.id FROM public.ingest_jobs j WHERE j.state='RUNNING' "
            "AND NOT EXISTS(SELECT 1 FROM pg_locks l WHERE l.locktype='advisory' "
            "AND l.pid=pg_backend_pid() AND l.classid=$1::oid "
            "AND l.objid=hashtext(j.id::text)::oid AND l.objsubid=2 AND l.granted)",
            _JOB_LOCK,
        ):
            if await conn.fetchval(
                "SELECT pg_try_advisory_xact_lock($1, hashtext($2::text))",
                _JOB_LOCK,
                str(row["id"]),
            ):
                updated = await conn.fetchval(
                    "UPDATE public.ingest_jobs SET state='FAILED',failure=$2,updated_at=now() "
                    "WHERE id=$1 AND state='RUNNING' RETURNING id",
                    row["id"],
                    json.dumps(
                        {
                            "type": "RuntimeError",
                            "message": "process ended without reporting",
                        }
                    ),
                )
                if updated is not None:
                    reaped.append(updated)
    return reaped


class GCDiagnostic(TypedDict):
    stage: str
    type: str
    sqlstate: str | None
    constraint: str | None
    message: str


class GCReport(TypedDict):
    reaped_jobs: list[UUID]
    building: list[UUID]
    retired: list[UUID]
    deleted_rows: dict[str, int]
    skipped: list[UUID]
    skipped_repositories: list[UUID]
    ignored_tables: list[str]
    errors: list[GCDiagnostic]


class GCError(ValueError):
    """A rolled-back cleanup with a safe, machine-readable diagnostic report."""

    def __init__(self, report: GCReport) -> None:
        self.report = report
        error = report["errors"][0]
        super().__init__(
            f"snapshot GC rolled back during {error['stage']}: {error['message']}"
        )


async def _preflight(conn: asyncpg.Connection) -> list[str]:
    pending, unknown = await db.schema_state(conn)
    if pending or unknown:
        raise ValueError(
            f"GC requires current known migrations; pending={pending}, unknown={unknown}"
        )
    tables = {
        row["name"]: row["uuid_column"]
        for row in await conn.fetch(
            "SELECT c.relname AS name, a.atttypid='uuid'::regtype AS uuid_column "
            "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind IN ('r','p','f') "
            "AND a.attname='snapshot_id' AND a.attnum>0 AND NOT a.attisdropped"
        )
    }
    retained = {"ingest_jobs", "ucm_repository_publications"}
    expected = set(_SNAPSHOT_TABLES) | retained
    invalid = sorted(name for name in expected if not tables.get(name))
    if invalid:
        raise ValueError(f"missing or non-UUID managed snapshot columns: {invalid}")
    managed = [*_SNAPSHOT_TABLES, "ucm_snapshots"]
    await conn.execute(
        "LOCK TABLE "
        + ",".join(f"public.{name}" for name in managed)
        + " IN ROW EXCLUSIVE MODE"
    )
    if await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM pg_inherits i "
        "JOIN pg_class p ON p.oid=i.inhparent JOIN pg_namespace pn ON pn.oid=p.relnamespace "
        "JOIN pg_class c ON c.oid=i.inhrelid JOIN pg_namespace cn ON cn.oid=c.relnamespace "
        "WHERE (pn.nspname='public' AND p.relname=ANY($1)) "
        "OR (cn.nspname='public' AND c.relname=ANY($1)))",
        managed,
    ):
        raise ValueError(
            "snapshot table inheritance/partitioning requires explicit GC support"
        )
    order = {name: i for i, name in enumerate(managed)}
    for fk in await conn.fetch(
        "SELECT k.conname AS name, n.nspname AS child_schema, c.relname AS child, "
        "p.relname AS parent, k.condeferrable AS deferred, k.confdeltype::text AS action, "
        "ARRAY(SELECT a.attname FROM unnest(k.conkey) AS col(num) "
        "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=col.num) AS columns "
        "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_class p ON p.oid=k.confrelid JOIN pg_namespace pn ON pn.oid=p.relnamespace "
        "WHERE k.contype='f' AND pn.nspname='public' AND p.relname=ANY($1)",
        managed,
    ):
        child, parent = fk["child"], fk["parent"]
        if fk["child_schema"] != "public" or child not in order:
            job_link = (
                child == "ingest_jobs"
                and fk["action"] == "n"
                and set(fk["columns"]) == {"snapshot_id"}
            )
            resolver_pin = (
                child in {"resolver_context_selections", "resolver_deployment_bindings"}
                and fk["action"] in ("a", "r")
                and set(fk["columns"]) == {"repository_id", "selected_snapshot_id"}
            )
            pointer = (
                child == "ucm_repository_publications"
                and fk["action"] in ("a", "r")
                and set(fk["columns"]) == {"repository_id", "snapshot_id"}
            )
            if (
                fk["child_schema"] == "public"
                and parent == "ucm_snapshots"
                and (job_link or pointer or resolver_pin)
            ):
                continue
            raise ValueError(
                f"unmanaged inbound FK: {fk['child_schema']}.{child}.{fk['name']}"
            )
        if (
            child == "search_documents"
            and parent == "search_index_generations"
            and fk["action"] == "c"
        ):
            continue  # Sealed documents may only be deleted by their generation cascade.
        if (not fk["deferred"] or fk["action"] in ("c", "n", "d")) and order[
            child
        ] >= order[parent]:
            raise ValueError(f"unsafe GC FK order: {fk['name']} ({child} -> {parent})")
    return sorted(set(tables) - expected)


async def _delete_snapshots(
    conn: asyncpg.Connection, ids: list[UUID]
) -> dict[str, int]:
    counts = {
        table: await conn.fetchval(
            f"SELECT count(*) FROM public.{table} WHERE snapshot_id=ANY($1)", ids
        )
        for table in _SNAPSHOT_TABLES
    }
    for table in _SNAPSHOT_TABLES:
        status = await conn.execute(
            f"DELETE FROM public.{table} WHERE snapshot_id=ANY($1)", ids
        )

    status = await conn.execute(
        "DELETE FROM public.ucm_snapshots WHERE id=ANY($1)", ids
    )
    counts["ucm_snapshots"] = int(status.removeprefix("DELETE "))
    if counts["ucm_snapshots"] != len(ids):
        raise ValueError("not every selected snapshot was deleted")
    return counts


async def collect_garbage(
    conn: asyncpg.Connection,
    *,
    building_older_than_hours: float | None = None,
    keep_retired: int | None = None,
) -> GCReport:
    """Atomically collect eligible, unpinned UCM snapshots after schema preflight.

    Existing snapshot lists remain compatible; counts/skips/diagnostics are additive.
    Errors expose an empty committed-result report through GCError.report.
    """
    if conn.is_in_transaction():
        raise ValueError("GC requires a connection without an active transaction")
    if building_older_than_hours is None and keep_retired is None:
        raise ValueError("GC requires a building age and/or retired retention")
    if building_older_than_hours is not None and (
        isinstance(building_older_than_hours, bool)
        or not isinstance(building_older_than_hours, (int, float))
        or not math.isfinite(building_older_than_hours)
        or building_older_than_hours < 0
    ):
        raise ValueError("building age must be finite and nonnegative")
    if keep_retired is not None and (type(keep_retired) is not int or keep_retired < 0):
        raise ValueError("kept RETIRED count must be a nonnegative integer")
    report: GCReport = {
        "reaped_jobs": [],
        "building": [],
        "retired": [],
        "deleted_rows": {},
        "skipped": [],
        "skipped_repositories": [],
        "ignored_tables": [],
        "errors": [],
    }
    stage = "preflight"
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock_shared($1)", db._MIGRATION_LOCK
            )
            report["ignored_tables"] = await _preflight(conn)
            await conn.execute("SET CONSTRAINTS ALL DEFERRED")
            await conn.execute("SET LOCAL code_crawler.gc = 'on'")
            stage = "reap"
            report["reaped_jobs"] = await reap(conn)
            stage = "select"
            candidates = await conn.fetch(
                "SELECT DISTINCT repository_id FROM public.ucm_snapshots "
                "WHERE (state='BUILDING' AND $1::double precision IS NOT NULL "
                "AND created_at<=now()-make_interval(secs=>$1*3600)) "
                "OR (state='RETIRED' AND $2::integer IS NOT NULL)",
                building_older_than_hours,
                keep_retired,
            )
            potential = {r["repository_id"] for r in candidates}
            repos = [
                r["id"]
                for r in await conn.fetch(
                    "SELECT id FROM public.ucm_repositories WHERE id=ANY($1) ORDER BY id FOR UPDATE SKIP LOCKED",
                    list(potential),
                )
            ]
            report["skipped_repositories"] = sorted(potential - set(repos))
            building = [
                r["id"]
                for r in await conn.fetch(
                    "SELECT s.id FROM public.ucm_snapshots s WHERE s.repository_id=ANY($1) "
                    "AND s.state='BUILDING' AND $2::double precision IS NOT NULL "
                    "AND s.created_at<=now()-make_interval(secs=>$2*3600)",
                    repos,
                    building_older_than_hours,
                )
            ]
            retired = (
                [
                    r["id"]
                    for r in await conn.fetch(
                        "SELECT id FROM (SELECT id,row_number() OVER (PARTITION BY repository_id "
                        "ORDER BY created_at DESC,id) AS position FROM public.ucm_snapshots "
                        "WHERE state='RETIRED' AND repository_id=ANY($1)) ranked WHERE position>$2",
                        repos,
                        keep_retired,
                    )
                ]
                if keep_retired is not None
                else []
            )
            await conn.execute("SELECT pg_advisory_xact_lock($1)", 4_217_003)
            locked = await conn.fetch(
                "SELECT s.id,s.state FROM public.ucm_snapshots s "
                "WHERE ((s.id=ANY($1) AND s.state='BUILDING') OR (s.id=ANY($2) AND s.state='RETIRED')) "
                "AND NOT EXISTS(SELECT 1 FROM public.ucm_repository_publications p WHERE p.snapshot_id=s.id) "
                "AND NOT EXISTS(SELECT 1 FROM public.ingest_jobs j WHERE j.state='RUNNING' "
                "AND (j.snapshot_id=s.id OR (s.state='BUILDING' AND j.repository_id=s.repository_id))) "
                "AND NOT EXISTS(SELECT 1 FROM public.resolver_context_selections pin WHERE pin.selected_snapshot_id=s.id) "
                "AND NOT EXISTS(SELECT 1 FROM public.resolver_deployment_bindings pin WHERE pin.selected_snapshot_id=s.id) "
                "ORDER BY s.id FOR UPDATE OF s SKIP LOCKED",
                building,
                retired,
            )
            selected = set()
            for row in locked:
                if await conn.fetchval(
                    snapshots._TRY_GC_LEASE, snapshots._SNAPSHOT_LOCK, str(row["id"])
                ):
                    selected.add(row["id"])
                    report[
                        "building" if row["state"] == "BUILDING" else "retired"
                    ].append(row["id"])
            report["skipped"] = sorted(set(building + retired) - selected)
            stage = "delete"
            if selected:
                report["deleted_rows"] = await _delete_snapshots(conn, sorted(selected))
            stage = "commit"
    except (
        asyncpg.PostgresError,
        asyncpg.InterfaceError,
        ValueError,
        RuntimeError,
    ) as error:
        report.update(reaped_jobs=[], building=[], retired=[], deleted_rows={})
        report["errors"] = [
            {
                "stage": stage,
                "type": type(error).__name__,
                "sqlstate": getattr(error, "sqlstate", None),
                "constraint": getattr(error, "constraint_name", None),
                "message": type(error).__name__
                if isinstance(error, (asyncpg.PostgresError, asyncpg.InterfaceError))
                else str(error),
            }
        ]
        # PostgreSQL DETAIL and exception messages may contain source bytes.
        raise GCError(report) from None
    return report
