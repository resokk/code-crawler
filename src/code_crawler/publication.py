"""Frozen-snapshot validation and short compare-and-swap publication transactions."""

import asyncio
import json
from collections import defaultdict
from uuid import UUID

import asyncpg

from code_crawler.ingestion import UcmBatch

_SUBTYPES = {
    "SQL_CONSTRUCTION": "ucm_sql_constructions",
    "SOURCE_FILE": "ucm_source_files",
    "SYMBOL": "ucm_symbols",
    "SCOPE": "ucm_scopes",
    "OCCURRENCE": "ucm_occurrences",
    "OPERATION": "ucm_operations",
    "VALUE": "ucm_values",
    "RELATION": "ucm_relations",
    "EXTERNAL_REFERENCE": "ucm_external_references",
}
_AUXILIARY = {
    "ucm_sql_variants": "construction_id",
    "ucm_sql_fragments": "candidate_id",
    "ucm_sql_partial_reasons": "candidate_id",
    "ucm_type_refs": "owner_id",
    "ucm_operation_values": "operation_id",
    "ucm_relation_candidates": "relation_id",
    "ucm_evidence": "owner_id",
    "ucm_coverage_reasons": "owner_id",
}


def _location(row: dict) -> dict | None:
    if row["source_file_id"] is None:
        return None
    return {
        "source_file_id": row["source_file_id"],
        "start": {"line": row["start_line"], "byte_column": row["start_byte_column"]},
        "end": {"line": row["end_line"], "byte_column": row["end_byte_column"]},
    }


def _ordered(rows: list[dict], column: str) -> list[dict]:
    ordered = sorted(rows, key=lambda row: row[column])
    if [row[column] for row in ordered] != list(range(len(ordered))):
        raise ValueError(f"noncontiguous {column} in snapshot")
    return ordered


def _reference(row: dict, prefix: str) -> dict | None:
    if row[prefix + "_id"] is None:
        return None
    return {"id": row[prefix + "_id"], "entity_type": row[prefix + "_type"]}


def _restore(repository_id: UUID, tables: dict[str, list[dict]]) -> UcmBatch:
    subtypes = {
        kind: {row["entity_id"]: row for row in tables[table]}
        for kind, table in _SUBTYPES.items()
    }
    auxiliary = {}
    for table, owner_column in _AUXILIARY.items():
        grouped = defaultdict(list)
        for row in tables[table]:
            grouped[row[owner_column]].append(row)
        auxiliary[table] = grouped
    documents = []
    for envelope in tables["ucm_entities"]:
        entity_id, kind = envelope["entity_id"], envelope["entity_type"]
        document = {
            "id": entity_id,
            "entity_type": kind,
            "contract_version": envelope["contract_version"],
            "repository_id": str(envelope["repository_id"]),
            "logical_key": envelope["logical_key"],
            "name": envelope["name"],
            "source_range": _location(envelope),
        }
        detail = {}
        if kind in subtypes:
            detail = subtypes[kind].pop(entity_id, None)
            if detail is None:
                raise ValueError(f"missing {kind} extension row")
            detail = {
                key: value
                for key, value in detail.items()
                if key not in ("snapshot_id", "entity_id", "entity_type")
            }
        types = defaultdict(list)
        for row in auxiliary["ucm_type_refs"].pop(entity_id, []):
            types[row["role"]].append(row)

        def refs(role: str, type_rows: dict = types) -> list[dict]:
            return [
                {
                    "name": row["name"],
                    "resolution": row["resolution"],
                    "target_symbol_id": row["target_symbol_id"],
                }
                for row in _ordered(type_rows.pop(role, []), "position")
            ]

        def single(role: str) -> dict | None:
            values = refs(role)
            if len(values) > 1:
                raise ValueError("multiple singleton TypeRefs")
            return values[0] if values else None

        if kind == "SYMBOL":
            detail["type_ref"] = single("TYPE")
            if detail["owner_key"] is not None:
                detail["signature"] = {
                    "parameter_types": refs("PARAMETER"),
                    "return_type": single("RETURN"),
                }
        elif kind == "SQL_CONSTRUCTION":
            detail["variants"] = []
            for row in _ordered(
                auxiliary["ucm_sql_variants"].pop(entity_id, []), "position"
            ):
                candidate = row["candidate_id"]
                fragments = [
                    {"kind": f["kind"], "text": f["text"], "source_range": _location(f)}
                    for f in _ordered(
                        auxiliary["ucm_sql_fragments"].pop(candidate, []), "ordinal"
                    )
                ]
                reasons = [
                    r["reason"]
                    for r in _ordered(
                        auxiliary["ucm_sql_partial_reasons"].pop(candidate, []),
                        "ordinal",
                    )
                ]
                detail["variants"].append(
                    {
                        "candidate_id": candidate,
                        "text": row["text"],
                        "partial": row["partial"],
                        "partial_reasons": reasons,
                        "fragments": fragments,
                    }
                )
        elif kind == "VALUE":
            detail["type_ref"] = single("TYPE")
            detail["literal"] = (
                json.loads(detail["literal"]) if detail["literal"] is not None else None
            )
        elif kind == "OPERATION":
            detail["callee"] = single("CALLEE")
            values = auxiliary["ucm_operation_values"].pop(entity_id, [])
            for direction, field in (
                ("INPUT", "input_value_ids"),
                ("OUTPUT", "output_value_ids"),
            ):
                detail[field] = [
                    row["value_id"]
                    for row in _ordered(
                        [row for row in values if row["direction"] == direction],
                        "position",
                    )
                ]
        elif kind == "RELATION":
            detail["source"] = _reference(detail, "source")
            candidates = auxiliary["ucm_relation_candidates"].pop(entity_id, [])
            detail["resolution"] = {
                "status": detail["resolution"],
                "target": _reference(detail, "target"),
                "reason": detail.pop("reason"),
                "candidates": [
                    _reference(row, "candidate")
                    for row in sorted(candidates, key=lambda row: row["candidate_id"])
                ],
            }
            for column in ("source_id", "source_type", "target_id", "target_type"):
                detail.pop(column)
        elif kind == "EXTERNAL_REFERENCE":
            detail["source"] = _reference(detail, "source")
            selector_kind = detail.pop("selector_kind")
            fields = {
                "SYMBOL": {
                    "qualified_name": "qualified_name",
                    "parameter_type_names": "parameter_type_names",
                },
                "HTTP": {
                    "method": "http_method",
                    "path": "http_path",
                    "service": "service",
                },
                "DATABASE": {
                    "connection": "connection",
                    "schema_name": "schema_name",
                    "table": "table_name",
                },
            }
            detail["selector"] = {
                "kind": selector_kind,
                **{
                    field: detail[column]
                    for field, column in fields[selector_kind].items()
                },
            }
            for column in (
                "source_id",
                "source_type",
                "qualified_name",
                "parameter_type_names",
                "http_method",
                "http_path",
                "service",
                "connection",
                "schema_name",
                "table_name",
            ):
                detail.pop(column)
        if types:
            raise ValueError("TypeRef role incompatible with owner")
        if kind in ("RELATION", "EXTERNAL_REFERENCE"):
            detail["coverage"] = {
                "capability": detail.pop("coverage_capability"),
                "analyzer_version": detail.pop("coverage_analyzer_version"),
                "status": detail.pop("coverage_status"),
                "reasons": [
                    row["reason"]
                    for row in _ordered(
                        auxiliary["ucm_coverage_reasons"].pop(entity_id, []), "ordinal"
                    )
                ],
            }
            detail["evidence"] = []
            for row in _ordered(
                auxiliary["ucm_evidence"].pop(entity_id, []), "ordinal"
            ):
                detail["evidence"].append(
                    {
                        "source_range": _location(row),
                        **{
                            field: row[field]
                            for field in (
                                "analyzer",
                                "analyzer_version",
                                "rule",
                                "description",
                            )
                        },
                    }
                )
        document.update(detail)
        documents.append(document)
    if any(rows for rows in subtypes.values()) or any(
        rows for rows in auxiliary.values()
    ):
        raise ValueError("unconsumed canonical rows")
    return UcmBatch.model_validate_json(
        json.dumps(
            {"repository_id": str(repository_id), "entities": documents},
            ensure_ascii=False,
        )
    )


def _require_free_connection(conn: asyncpg.Connection) -> None:
    if conn.is_in_transaction():
        raise ValueError(
            "publication API requires a connection without an active transaction"
        )


async def load_snapshot_batch(conn: asyncpg.Connection, snapshot_id: UUID) -> UcmBatch:
    """Read and validate a frozen canonical snapshot without changing its state."""
    snapshot = await conn.fetchrow(
        "SELECT repository_id,state FROM public.ucm_snapshots WHERE id=$1", snapshot_id
    )
    if snapshot is None or snapshot["state"] == "BUILDING":
        raise ValueError("reading batch requires a frozen snapshot")
    tables = {}
    for table in ("ucm_entities", *_SUBTYPES.values(), *_AUXILIARY):
        tables[table] = [
            dict(row)
            for row in await conn.fetch(
                f"SELECT * FROM public.{table} WHERE snapshot_id=$1", snapshot_id
            )
        ]
    return await asyncio.to_thread(_restore, snapshot["repository_id"], tables)


async def validate_snapshot(conn: asyncpg.Connection, snapshot_id: UUID) -> int:
    """Freeze and validate all stored facts, then record readiness; return entity count."""
    _require_free_connection(conn)
    async with conn.transaction():
        snapshot = await conn.fetchrow(
            "SELECT * FROM public.ucm_snapshots WHERE id=$1 FOR UPDATE", snapshot_id
        )
        if snapshot is None:
            raise ValueError("snapshot does not exist")
        if snapshot["state"] == "READY":
            count = await conn.fetchval(
                "SELECT entity_count FROM public.ucm_snapshot_validations WHERE snapshot_id=$1",
                snapshot_id,
            )
            if count is None:
                raise ValueError("READY snapshot has no validation receipt")
            return count
        if snapshot["state"] not in ("BUILDING", "VALIDATING"):
            raise ValueError("validation requires BUILDING or VALIDATING snapshot")
        await conn.execute(
            "UPDATE public.ucm_snapshots SET state='VALIDATING' WHERE id=$1",
            snapshot_id,
        )
    batch = await load_snapshot_batch(conn, snapshot_id)
    count = len(batch.entities)
    async with conn.transaction():
        state = await conn.fetchval(
            "SELECT state FROM public.ucm_snapshots WHERE id=$1 FOR UPDATE", snapshot_id
        )
        if state == "READY":
            return count
        if state != "VALIDATING":
            raise ValueError("snapshot state changed during validation")
        await conn.execute(
            "INSERT INTO public.ucm_snapshot_validations(snapshot_id,entity_count) VALUES ($1,$2)",
            snapshot_id,
            count,
        )
        await conn.execute(
            "UPDATE public.ucm_snapshots SET state='READY' WHERE id=$1", snapshot_id
        )
    return count


async def _publish(
    conn: asyncpg.Connection,
    repository_id: UUID,
    snapshot_id: UUID,
    expected_snapshot_id: UUID | None,
    rollback: bool,
) -> None:
    _require_free_connection(conn)
    async with conn.transaction():
        if not await conn.fetchval(
            "SELECT id FROM public.ucm_repositories WHERE id=$1 FOR UPDATE",
            repository_id,
        ):
            raise ValueError("repository does not exist")
        current = await conn.fetchval(
            "SELECT snapshot_id FROM public.ucm_repository_publications WHERE repository_id=$1",
            repository_id,
        )
        if current != expected_snapshot_id:
            raise ValueError(
                "publication pointer changed; refresh expected_snapshot_id"
            )
        target = await conn.fetchrow(
            "SELECT repository_id,state FROM public.ucm_snapshots WHERE id=$1 FOR UPDATE",
            snapshot_id,
        )
        if target is None or target["repository_id"] != repository_id:
            raise ValueError("snapshot missing or belongs to another repository")
        if current == snapshot_id and target["state"] == "PUBLISHED":
            return
        required = "RETIRED" if rollback else "READY"
        if target["state"] != required:
            raise ValueError(f"publication requires {required} snapshot")
        if not await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM public.ucm_snapshot_validations WHERE snapshot_id=$1)",
            snapshot_id,
        ):
            raise ValueError("snapshot has no validation receipt")
        if current is not None:
            await conn.execute(
                "UPDATE public.ucm_snapshots SET state='RETIRED' WHERE id=$1", current
            )
        await conn.execute(
            "UPDATE public.ucm_snapshots SET state='PUBLISHED' WHERE id=$1", snapshot_id
        )
        await conn.execute(
            "INSERT INTO public.ucm_repository_publications(repository_id,snapshot_id) VALUES ($1,$2) ON CONFLICT (repository_id) DO UPDATE SET snapshot_id=EXCLUDED.snapshot_id,updated_at=clock_timestamp()",
            repository_id,
            snapshot_id,
        )


async def publish_snapshot(
    conn: asyncpg.Connection,
    repository_id: UUID,
    snapshot_id: UUID,
    *,
    expected_snapshot_id: UUID | None,
) -> None:
    """Atomically publish a validated READY snapshot using an expected-pointer check."""
    await _publish(
        conn, repository_id, snapshot_id, expected_snapshot_id, rollback=False
    )


async def rollback_publication(
    conn: asyncpg.Connection,
    repository_id: UUID,
    snapshot_id: UUID,
    *,
    expected_snapshot_id: UUID | None,
) -> None:
    """Atomically restore a validated RETIRED snapshot without changing its facts."""
    await _publish(
        conn, repository_id, snapshot_id, expected_snapshot_id, rollback=True
    )
