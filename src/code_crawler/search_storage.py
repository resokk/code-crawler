"""Repository-authorized derivative generations; canonical facts are never written."""

import asyncio
import hashlib
import json
from collections.abc import Callable, Collection
from uuid import UUID, uuid4

import asyncpg

from code_crawler.data_security import (
    DEFAULT_POLICY,
    DataSecurityError,
    SecretPolicy,
    structural_value,
)
from code_crawler.ingestion import UcmBatch
from code_crawler.publication import load_snapshot_batch
from code_crawler.search_documents import _project_raw
from code_crawler.ucm import Relation

PROJECTION_VERSION = "search-documents-v2-security"


def _authorize(repository_id: UUID, allowed_repository_ids: Collection[UUID]) -> None:
    if repository_id not in allowed_repository_ids:
        raise PermissionError("repository access denied")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _records(
    batch: UcmBatch,
    redact: Callable[[str], str],
    *,
    security_policy: SecretPolicy = DEFAULT_POLICY,
    report: dict | None = None,
) -> list[tuple]:
    policy = redact

    def redact(text: str) -> str:
        try:
            value = policy(text)
        except Exception:  # noqa: BLE001 -- caller exceptions can contain source secrets.
            raise DataSecurityError("redaction policy failed") from None
        if not isinstance(value, str):
            raise TypeError("redaction policy must return str")
        return value

    facts = {entity.id: entity for entity in batch.entities}
    relations_by_entity = {}
    for relation in sorted(batch.entities, key=lambda e: e.id):
        if not isinstance(relation, Relation):
            continue
        ids = {relation.source.id, *(c.id for c in relation.resolution.candidates)}
        if relation.resolution.target:
            ids.add(relation.resolution.target.id)
        for entity_id in ids:
            relations_by_entity.setdefault(entity_id, []).append(
                relation.model_dump(mode="json")
            )
    records = []
    aggregate = {
        "policy_version": security_policy.version,
        "status": "COMPLETE",
        "redacted_documents": 0,
        "skipped_documents": 0,
        "skipped_entity_ids": [],
        "categories": [],
    }
    for document in _project_raw(batch.entities):
        # SQL text is source, while the remaining lines describe recorded facts.
        source = None
        summary = document.text
        title = document.title
        if document.kind in ("SQL_STATEMENT", "ORM_QUERY"):
            statement = facts[document.entity_id]
            if statement.text:
                summary = summary.replace("\n" + statement.text, "", 1)
                source = statement.text
            if document.kind == "SQL_STATEMENT":
                title = f"{statement.operation} statement"
        content = {
            "title": title,
            "summary": summary,
            "target_language": "en",
            "source_language": document.language,
            "path": document.path,
            "redacted_source": source,
        }
        entity = facts[document.entity_id]
        relations = relations_by_entity.get(entity.id, [])

        # Preserve statuses, Evidence and Coverage, but apply the same policy to
        # every string (including reasons and evidence descriptions).
        def clean(value: object, field: str = "") -> object:
            if isinstance(value, str):
                changed = redact(value)
                if structural_value(field, value) and changed != value:
                    raise DataSecurityError(
                        "redaction policy changed a structural fact"
                    )
                return changed
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, dict):
                return {key: clean(item, key) for key, item in value.items()}
            return value

        provenance = {
            "entity_id": entity.id,
            "source_range": entity.source_range.model_dump(mode="json")
            if entity.source_range
            else None,
            "relations": relations,
        }
        original = {"content": content, "provenance": provenance}
        safe, before = security_policy.clean(original)
        aggregate["categories"] = sorted(
            set(aggregate["categories"]) | {f["category"] for f in before["findings"]}
        )
        if safe is None:
            aggregate["status"] = "PARTIAL"
            aggregate["skipped_documents"] += 1
            if len(aggregate["skipped_entity_ids"]) < 256:
                aggregate["skipped_entity_ids"].append(entity.id)
            continue
        safe, after = security_policy.clean(clean(safe), context=original)
        aggregate["categories"] = sorted(
            set(aggregate["categories"]) | {f["category"] for f in after["findings"]}
        )
        if safe is None:
            aggregate["status"] = "PARTIAL"
            aggregate["skipped_documents"] += 1
            if len(aggregate["skipped_entity_ids"]) < 256:
                aggregate["skipped_entity_ids"].append(entity.id)
            continue
        content, provenance = safe["content"], safe["provenance"]
        findings = before["findings"] + after["findings"]
        provenance["redaction"] = {
            **before,
            "findings": findings,
            "status": "PARTIAL" if findings else "COMPLETE",
        }
        if findings:
            aggregate["status"] = "PARTIAL"
            aggregate["redacted_documents"] += 1
        encoded = _json(content)
        records.append(
            (
                document.id,
                document.entity_id,
                document.kind,
                encoded,
                hashlib.sha256(encoded.encode()).hexdigest(),
                _json(provenance),
            )
        )
    aggregate["skipped_ids_truncated"] = aggregate["skipped_documents"] > len(
        aggregate["skipped_entity_ids"]
    )
    if report is not None:
        report.update(aggregate)
    return records


async def rebuild_search_documents(
    conn: asyncpg.Connection,
    repository_id: UUID,
    snapshot_id: UUID,
    *,
    allowed_repository_ids: Collection[UUID],
    policy_version: str,
    redact: Callable[[str], str],
    expected_generation_id: UUID | None,
    security_policy: SecretPolicy = DEFAULT_POLICY,
) -> UUID:
    """Build and atomically publish a complete generation for a validated snapshot.

    The trusted caller supplies authorization and a deterministic secret policy.
    Failure or cancellation leaves the previous generation visible. Reindexing
    never updates the canonical snapshot or its publication pointer.
    """
    _authorize(repository_id, allowed_repository_ids)
    if conn.is_in_transaction():
        raise ValueError("search rebuild requires a connection without a transaction")
    if not policy_version.strip():
        raise ValueError("policy_version must not be empty")
    SecretPolicy("reject").clean(policy_version)
    generation_id = uuid4()
    async with conn.transaction():
        snapshot = await conn.fetchrow(
            "SELECT repository_id,state FROM public.ucm_snapshots WHERE id=$1",
            snapshot_id,
        )
        if snapshot is None or snapshot["repository_id"] != repository_id:
            raise ValueError("snapshot missing or belongs to another repository")
        if snapshot["state"] not in ("READY", "PUBLISHED", "RETIRED"):
            raise ValueError("search rebuild requires a validated snapshot")
        batch = await load_snapshot_batch(conn, snapshot_id)
        security_report = {}
        records = await asyncio.to_thread(
            _records,
            batch,
            redact,
            security_policy=security_policy,
            report=security_report,
        )
        await conn.execute(
            """INSERT INTO public.search_index_generations
               (id,repository_id,snapshot_id,projection_version,policy_version,document_count,security_report)
               VALUES ($1,$2,$3,$4,$5,$6,$7)""",
            generation_id,
            repository_id,
            snapshot_id,
            PROJECTION_VERSION,
            f"{security_policy.version}/{policy_version}",
            len(records),
            _json(security_report),
        )
        await conn.copy_records_to_table(
            "search_documents",
            schema_name="public",
            columns=(
                "repository_id",
                "snapshot_id",
                "generation_id",
                "document_id",
                "entity_id",
                "document_type",
                "content",
                "content_sha256",
                "provenance",
            ),
            records=(
                (repository_id, snapshot_id, generation_id, *row) for row in records
            ),
        )
        await conn.execute(
            "UPDATE public.search_index_generations SET sealed=true WHERE id=$1",
            generation_id,
        )
        # Serialize the final compare-and-swap, including the first publication.
        await conn.fetchval(
            "SELECT id FROM public.ucm_repositories WHERE id=$1 FOR UPDATE",
            repository_id,
        )
        current = await conn.fetchval(
            """SELECT generation_id FROM public.search_index_publications
               WHERE repository_id=$1 AND snapshot_id=$2""",
            repository_id,
            snapshot_id,
        )
        if current != expected_generation_id:
            raise ValueError("search generation pointer changed")
        await conn.execute(
            """INSERT INTO public.search_index_publications
               (repository_id,snapshot_id,generation_id) VALUES ($1,$2,$3)
               ON CONFLICT (repository_id,snapshot_id)
               DO UPDATE SET generation_id=EXCLUDED.generation_id""",
            repository_id,
            snapshot_id,
            generation_id,
        )
    return generation_id


def _secure_report(row: dict) -> dict:
    report = json.loads(row["security_report"])
    versions = {SecretPolicy(action).version for action in ("mask", "skip", "reject")}
    if (
        row["projection_version"] != PROJECTION_VERSION
        or not isinstance(report.get("policy_version"), str)
        or report.get("policy_version") not in versions
    ):
        raise LookupError("secure search generation rebuild required")
    return report


async def read_search_documents(
    conn: asyncpg.Connection,
    repository_id: UUID,
    *,
    allowed_repository_ids: Collection[UUID],
    snapshot_id: UUID | None = None,
    after_document_id: str = "",
    limit: int = 100,
) -> list[dict]:
    """Read one complete generation of the currently published canonical snapshot.

    Supply snapshot_id from the first page to prevent silently switching snapshots.
    For multiple pages pin a read-only REPEATABLE READ transaction. An unavailable
    generation is reported explicitly rather than falling back to stale source.
    """
    _authorize(repository_id, allowed_repository_ids)
    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    rows = await conn.fetch(
        """SELECT p.snapshot_id, g.id AS generation_id, g.projection_version,
                  g.policy_version, g.document_count, g.security_report, d.document_id, d.entity_id,
                  d.document_type, d.content, d.content_sha256, d.provenance
           FROM public.ucm_repository_publications p
           LEFT JOIN public.search_index_publications s
             ON s.repository_id=p.repository_id AND s.snapshot_id=p.snapshot_id
           LEFT JOIN public.search_index_generations g ON g.id=s.generation_id
           LEFT JOIN LATERAL (
               SELECT * FROM public.search_documents d
               WHERE d.generation_id=g.id AND d.document_id>$3
               ORDER BY d.document_id LIMIT $4
           ) d ON true
           WHERE p.repository_id=$1 AND ($2::uuid IS NULL OR p.snapshot_id=$2)
           ORDER BY d.document_id""",
        repository_id,
        snapshot_id,
        after_document_id,
        limit,
    )
    if not rows or rows[0]["generation_id"] is None:
        raise LookupError("search generation unavailable for published snapshot")
    _secure_report(rows[0])

    def restore() -> list[dict]:
        result = []
        for row in rows:
            if row["document_id"] is None:
                continue
            item = dict(row)
            item["content"] = json.loads(item["content"])
            item["provenance"] = {
                **json.loads(item["provenance"]),
                "repository_id": str(repository_id),
                "snapshot_id": str(item["snapshot_id"]),
                "generation_id": str(item["generation_id"]),
            }
            item["security_report"] = _secure_report(item)
            _, report = SecretPolicy().clean(item)
            if report["findings"]:
                raise LookupError("secure search generation rebuild required")
            result.append(item)
        return result

    return await asyncio.to_thread(restore)


async def read_search_security_report(
    conn: asyncpg.Connection,
    repository_id: UUID,
    *,
    allowed_repository_ids: Collection[UUID],
) -> dict:
    """Read current generation diagnostics even when skip policy yielded no documents."""
    _authorize(repository_id, allowed_repository_ids)
    row = await conn.fetchrow(
        "SELECT g.security_report,g.projection_version FROM public.ucm_repository_publications p "
        "JOIN public.search_index_publications s USING(repository_id,snapshot_id) "
        "JOIN public.search_index_generations g ON g.id=s.generation_id WHERE p.repository_id=$1",
        repository_id,
    )
    if not row:
        raise LookupError("secure search generation rebuild required")
    report = _secure_report(row)
    _, findings = await asyncio.to_thread(SecretPolicy().clean, report)
    if findings["findings"]:
        raise LookupError("secure search generation rebuild required")
    return report
