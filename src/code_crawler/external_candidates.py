"""Bounded read-only selector resolution; proof concerns identity, never runtime edges."""

import json
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import asyncpg
from pydantic import Field, model_validator

from code_crawler import discovery, resolver_cache
from code_crawler.reader import selected_reader
from code_crawler.resolver_context import ResolverContext, verify_context
from code_crawler.snapshots import pin_snapshot
from code_crawler.ucm import (
    Certainty,
    ContractModel,
    Coverage,
    DatabaseSelector,
    EntityId,
    EntityRef,
    EntityType,
    HttpSelector,
    Position,
    SourceRange,
    SymbolSelector,
    Text,
)

VERSION = "2"
_UNKNOWN_TYPE = re.compile(
    r"(?<![\w.$])(?:kotlin\.unknown|groovy\.dynamic|vbscript\.Variant|unknown|any)(?![\w.$])|<unknown>"
)


class EvidencePath(ContractModel):
    repository_id: UUID
    snapshot_id: UUID
    entity_id: EntityId
    generation: UUID | None
    source_range: SourceRange | None
    path: str | None
    content_sha256: str | None
    rule: Text
    available: bool
    unavailable_reason: str | None = None


class ExternalCandidate(ContractModel):
    repository_key: Text
    repository_id: UUID
    snapshot_id: UUID
    generation: UUID
    target: EntityRef
    certainty: Certainty
    contract_id: EntityId | None = None
    coverage: Coverage
    evidence: EvidencePath
    rule: Text


class CandidateResolution(ContractModel):
    contract_version: Literal[1] = 1
    proof_scope: Literal["DECLARATION_IDENTITY"] = "DECLARATION_IDENTITY"
    source_repository_id: UUID
    source_snapshot_id: UUID
    external_reference_id: EntityId
    origin: EntityRef
    context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["RESOLVED", "AMBIGUOUS", "PARTIAL", "UNRESOLVED"]
    target: ExternalCandidate | None
    candidates: tuple[ExternalCandidate, ...]
    source_evidence: tuple[EvidencePath, ...]
    reference_certainty: Certainty
    reference_coverage: Coverage
    coverage: Coverage
    reasons: tuple[Text, ...]
    truncated: bool
    unavailable_repositories: tuple[str, ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> "CandidateResolution":
        if self.status == "RESOLVED":
            if (
                self.target is None
                or self.candidates != (self.target,)
                or self.reasons
                or self.truncated
                or self.unavailable_repositories
            ):
                raise ValueError(
                    "resolved identity requires one complete untruncated proof"
                )
        elif self.target is not None or not self.reasons:
            raise ValueError("incomplete resolution needs reasons and no target")
        if self.status == "AMBIGUOUS" and len(self.candidates) < 2:
            raise ValueError("ambiguity requires multiple candidates")
        if self.status == "UNRESOLVED" and self.candidates:
            raise ValueError("unresolved result cannot contain candidates")
        return self


@dataclass(frozen=True)
class SelectorLookup:
    kind: str
    key: tuple
    complete: bool
    reasons: tuple[str, ...] = ()


def normalize_selector(
    selector: SymbolSelector | HttpSelector | DatabaseSelector,
) -> SelectorLookup:
    """Preserve selector-specific identity without inventing global aliases or targets."""
    if isinstance(selector, SymbolSelector):
        for prefix, kind in (
            ("bpmn.process::", "BPMN_PROCESS"),
            ("bpmn.worker::", "BPMN_WORKER"),
            ("kafka.topic::", "KAFKA_TOPIC"),
        ):
            if selector.qualified_name.startswith(prefix):
                return SelectorLookup(
                    kind,
                    (selector.qualified_name[len(prefix) :],),
                    False,
                    ("framework binding/deployment semantics are not proven",),
                )
        framework_unknown = selector.qualified_name.startswith(
            ("bpmn.", "kafka.", "cft.", "plplus.", "graphql.", "openapi.")
        )
        known = selector.parameter_type_names is not None
        unknown_types = known and any(
            t in ("?", "*") or _UNKNOWN_TYPE.search(t) is not None
            for t in selector.parameter_type_names
        )
        dynamic = any(
            part in selector.qualified_name
            for part in ("${", "#{", "<unknown>", "*", "?")
        )
        return SelectorLookup(
            "SYMBOL_SIGNATURE" if known else "SYMBOL",
            (selector.qualified_name, selector.parameter_type_names)
            if known
            else (selector.qualified_name,),
            known and not dynamic and not framework_unknown and not unknown_types,
            ("unsupported framework selector semantics",)
            if framework_unknown
            else ("unknown parameter type identity",)
            if unknown_types
            else ("dynamic symbol selector",)
            if dynamic
            else ()
            if known
            else ("unknown signature; name alone is not proof",),
        )
    if isinstance(selector, HttpSelector):
        complete = (
            selector.service is not None
            and "{" not in selector.path
            and "${" not in selector.service
        )
        return SelectorLookup(
            "HTTP",
            (selector.service, selector.method, selector.path),
            complete,
            () if complete else ("HTTP service/path is incomplete or dynamic",),
        )
    return SelectorLookup(
        "DATABASE",
        (selector.connection, selector.schema_name, selector.table),
        False,
        ("database alias requires an explicit canonical connection context",),
    )


def _coverage(complete=False, reasons=()):
    return Coverage(
        capability="external.reference.candidates",
        analyzer_version=VERSION,
        status="COMPLETE" if complete else "PARTIAL",
        reasons=() if complete else reasons or ("candidate-only discovery",),
    )


def _path(selection, entity_id, location, metadata, rule):
    available = bool(location and metadata and metadata["archived"])
    return EvidencePath(
        repository_id=selection.repository_id,
        snapshot_id=selection.snapshot_id,
        entity_id=entity_id,
        generation=selection.generation,
        source_range=location,
        path=metadata["path"] if metadata else None,
        content_sha256=metadata["content_sha256"] if metadata else None,
        rule=rule,
        available=available,
        unavailable_reason=None if available else "source range/archive unavailable",
    )


async def _source_evidence(conn, reference, source):
    evidence = reference.evidence[:32]
    rows = await conn.fetch(
        "SELECT f.entity_id,f.path,f.content_sha256,(a.source_file_id IS NOT NULL) AS archived "
        "FROM public.ucm_source_files f LEFT JOIN public.ucm_snapshot_sources a "
        "ON a.snapshot_id=f.snapshot_id AND a.source_file_id=f.entity_id AND a.content_sha256=f.content_sha256 "
        "WHERE f.snapshot_id=$1 AND f.entity_id=ANY($2)",
        source.snapshot_id,
        [e.source_range.source_file_id for e in evidence],
    )
    metadata = {r["entity_id"]: r for r in rows}
    return tuple(
        _path(
            source,
            reference.id,
            e.source_range,
            metadata.get(e.source_range.source_file_id),
            e.rule,
        )
        for e in evidence
    )


async def _database_lookup(conn, selector, source, origin_file_id):
    if origin_file_id is None:
        return None, "database alias origin has no explicit source-file context"
    contexts = await conn.fetch(
        "SELECT DISTINCT c.database_key,c.version_key,v.catalog_name,c.schema_fingerprint,c.entity_id "
        "FROM public.ucm_database_contexts c JOIN public.ucm_database_schema_versions v "
        "ON v.database_key=c.database_key AND v.version_key=c.version_key "
        "WHERE c.snapshot_id=$1 AND c.connection_key=$2 AND c.projection_file_id=$3 ORDER BY c.entity_id LIMIT 2",
        source.snapshot_id,
        selector.connection,
        origin_file_id,
    )
    if len(contexts) != 1:
        return None, "connection alias has no unique canonical database identity"
    context = contexts[0]
    schema = selector.schema_name
    if schema is None:
        paths = await conn.fetch(
            "SELECT schema_name FROM public.ucm_database_search_paths WHERE snapshot_id=$1 AND context_id=$2 ORDER BY position LIMIT 2",
            source.snapshot_id,
            context["entity_id"],
        )
        if len(paths) != 1:
            return None, "database schema/search path is not uniquely constrained"
        schema = paths[0]["schema_name"]
    return (
        context["database_key"],
        context["version_key"],
        context["catalog_name"],
        schema,
        selector.table,
    ), None


async def _resolve(conn, source_key, reference_id, context, grants, limit, cache_read):
    unavailable = await verify_context(conn, context, allowed_repositories=grants)
    for selection in sorted(context.selections, key=lambda s: s.snapshot_id):
        await pin_snapshot(conn, selection.snapshot_id)
    selections = {s.repository_key: s for s in context.selections}
    source = selections[source_key]
    if cache_read and not unavailable:
        cached = await resolver_cache._read_cached_resolution(
            conn, source_key, reference_id, context, limit, VERSION
        )
        if cached is not None:
            return cached
    elif cache_read:
        resolver_cache.event("BYPASS", "GENERATION_UNAVAILABLE", context)
    async with selected_reader(
        conn, source_key, source.snapshot_id, allowed_repositories=grants
    ) as view:
        reference = await view.get_entity(reference_id)
        if reference.entity_type != EntityType.EXTERNAL_REFERENCE:
            raise ValueError(
                "entity is not an ExternalReference in the selected source snapshot"
            )
        origin_file_id = None
        if isinstance(reference.selector, DatabaseSelector):
            origin = await view.get_entity(reference.source.id)
            if origin.source_range:
                origin_file_id = origin.source_range.source_file_id
    lookup = normalize_selector(reference.selector)
    reasons = list(lookup.reasons)
    proofs = await _source_evidence(conn, reference, source)
    if len(reference.evidence) > 32:
        reasons.append("source Evidence fanout truncated")
    if any(not p.available for p in proofs):
        reasons.append("source Evidence archive unavailable")
    if (
        reference.certainty != Certainty.STATIC_PROVEN
        or reference.coverage.status != "COMPLETE"
    ):
        reasons.append(
            "source fact certainty/coverage does not establish a complete binding"
        )
    db_key = None
    if isinstance(reference.selector, DatabaseSelector):
        db_key, error = await _database_lookup(
            conn, reference.selector, source, origin_file_id
        )
        if error:
            reasons.append(error)
        else:
            reasons = [
                r
                for r in reasons
                if r
                != "database alias requires an explicit canonical connection context"
            ]
            lookup = SelectorLookup("DATABASE", db_key, True)
    rows = []
    bounded = tuple(
        s
        for s in context.selections
        if s.repository_key not in unavailable
        and (
            reference.repository_hint is None
            or reference.repository_hint == s.repository_key
        )
        and (
            reference.version_hint is None
            or reference.version_hint in (s.commit_hash, str(s.snapshot_id))
        )
    )
    if (
        isinstance(reference.selector, HttpSelector)
        and reference.selector.service is not None
    ):
        bounded = tuple(s for s in bounded if reference.selector.service in s.services)
        if not bounded:
            reasons.append(
                "HTTP service has no authoritative deployment binding in the selected context"
            )
    if isinstance(reference.selector, HttpSelector):
        reasons.append(
            "HTTP operation service identity is not declared by OpenAPI operation facts"
        )
    supported = discovery.COVERAGE[lookup.kind] != "UNSUPPORTED"
    if not supported:
        reasons.append(f"{lookup.kind} target declaration producer is unsupported")
    if reference.version_hint and not bounded:
        reasons.append("version hint is not verified by any selected commit/snapshot")
    if supported and bounded and (lookup.kind != "DATABASE" or db_key):
        # A database selector can match table/view kinds, but never schema/column or another database version.
        keys = [lookup.key]
        if isinstance(reference.selector, HttpSelector):
            keys = [(None, reference.selector.method, reference.selector.path)]
        if db_key:
            database, version, catalog, schema, table = db_key
            keys = [
                (database, version, catalog, schema, k, table, None)
                for k in ("TABLE", "VIEW", "MATERIALIZED_VIEW", "FOREIGN_TABLE")
            ]
        key_match = (
            "md5(e.lookup_key::text)=md5(k.value::text) AND e.lookup_key=k.value"
        )
        if isinstance(reference.selector, HttpSelector):
            key_match = (
                "md5(CASE WHEN e.kind='DATABASE' THEN COALESCE(e.lookup_key->>6,e.lookup_key->>5,e.lookup_key->>3) "
                "WHEN e.kind='HTTP' THEN e.lookup_key->>2 ELSE e.lookup_key->>0 END)=md5(k.value->>2) "
                "AND e.lookup_key->>2=k.value->>2 AND e.lookup_key->>1=k.value->>1 AND e.lookup_key->0=k.value->0"
            )
        rows = await conn.fetch(
            f"""
            SELECT e.*,r.repository_key,f.path,f.content_sha256,(a.source_file_id IS NOT NULL) AS archived
            FROM public.search_discovery_entries e
            JOIN jsonb_array_elements($5::jsonb) AS k(value) ON {key_match}
            JOIN public.ucm_repositories r ON r.id=e.repository_id
            JOIN public.search_discovery_generations g ON g.snapshot_id=e.snapshot_id AND g.generation=e.generation
            LEFT JOIN public.ucm_source_files f ON f.snapshot_id=e.snapshot_id AND f.entity_id=e.source_file_id
            LEFT JOIN public.ucm_snapshot_sources a ON a.snapshot_id=f.snapshot_id AND a.source_file_id=f.entity_id AND a.content_sha256=f.content_sha256
            WHERE (e.snapshot_id,e.generation) IN (SELECT * FROM unnest($1::uuid[],$2::uuid[]))
              AND e.kind=$3 AND g.projector_version=$4 AND g.state='READY'
            ORDER BY r.repository_key,e.snapshot_id,e.entity_id LIMIT $6
            """,
            [s.snapshot_id for s in bounded],
            [s.generation for s in bounded],
            lookup.kind,
            discovery.VERSION,
            json.dumps(keys, ensure_ascii=False),
            limit + 1,
        )
    truncated = len(rows) > limit
    if truncated:
        reasons.append("candidate fanout exceeded limit")
    if unavailable:
        reasons.append("selected catalog generation unavailable or superseded")
    candidates = []
    for row in rows[:limit]:
        selection = selections[row["repository_key"]]
        location = None
        if row["source_file_id"]:
            location = SourceRange(
                source_file_id=row["source_file_id"],
                start=Position(
                    line=row["start_line"], byte_column=row["start_byte_column"]
                ),
                end=Position(line=row["end_line"], byte_column=row["end_byte_column"]),
            )
        evidence = _path(selection, row["entity_id"], location, row, row["rule"])
        candidates.append(
            ExternalCandidate(
                repository_key=selection.repository_key,
                repository_id=selection.repository_id,
                snapshot_id=selection.snapshot_id,
                generation=selection.generation,
                target=EntityRef(
                    entity_type=EntityType(row["entity_type"]), id=row["entity_id"]
                ),
                certainty=Certainty.INFERRED,
                contract_id=json.loads(row["qualifier"]).get("contract_id"),
                coverage=_coverage(),
                evidence=evidence,
                rule=f"selector.exact.{lookup.kind.lower()}",
            )
        )
    if truncated or unavailable:
        status = "PARTIAL"
    elif len(candidates) > 1:
        status = "AMBIGUOUS"
        reasons.append("multiple compatible declaration identities")
    elif not candidates:
        status = "UNRESOLVED"
        reasons.append("no compatible declaration in selected context")
    else:
        if not candidates[0].evidence.available:
            reasons.append("target Evidence archive unavailable")
        status = "PARTIAL" if reasons or not lookup.complete else "RESOLVED"
    target = None
    if status == "RESOLVED":
        candidates[0] = candidates[0].model_copy(
            update={"certainty": Certainty.STATIC_PROVEN, "coverage": _coverage(True)}
        )
        target = candidates[0]
    coverage = _coverage(status == "RESOLVED", tuple(dict.fromkeys(reasons)))
    if not supported:
        coverage = Coverage(
            capability="external.reference.candidates",
            analyzer_version=VERSION,
            status="UNSUPPORTED",
            reasons=(f"{lookup.kind} target declarations unavailable",),
        )
    return CandidateResolution(
        source_repository_id=source.repository_id,
        source_snapshot_id=source.snapshot_id,
        external_reference_id=reference.id,
        origin=reference.source,
        context_fingerprint=context.fingerprint,
        status=status,
        target=target,
        candidates=tuple(candidates),
        source_evidence=proofs,
        reference_certainty=reference.certainty,
        reference_coverage=reference.coverage,
        coverage=coverage,
        reasons=tuple(dict.fromkeys(reasons)),
        truncated=truncated,
        unavailable_repositories=unavailable,
    )


async def _resolve_request(
    conn: asyncpg.Connection,
    source_repository_key: str,
    reference_id: str,
    context: ResolverContext,
    *,
    allowed_repositories: frozenset[str],
    limit: int = 50,
    cache_read: bool,
) -> CandidateResolution:
    """Resolve declaration candidates within exact authorized versions; never create runtime edges."""
    context = ResolverContext.model_validate_json(context.model_dump_json())
    keys = tuple(s.repository_key for s in context.selections)
    discovery.authorize(keys, allowed_repositories)
    if source_repository_key not in keys:
        raise ValueError("source repository is not selected by resolver context")
    if (
        not isinstance(reference_id, str)
        or re.fullmatch(r"ucm:[0-9a-f]{64}", reference_id) is None
    ):
        raise ValueError("invalid canonical entity ID")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= discovery.MAX_LIMIT
    ):
        raise ValueError("invalid candidate limit")
    if conn.is_in_transaction():
        if (
            await conn.fetchval("SHOW transaction_isolation")
            not in ("repeatable read", "serializable")
            or await conn.fetchval("SHOW transaction_read_only") != "on"
        ):
            raise ValueError("resolver requires read-only repeatable-read transaction")
        return await _resolve(
            conn,
            source_repository_key,
            reference_id,
            context,
            allowed_repositories,
            limit,
            cache_read,
        )
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        return await _resolve(
            conn,
            source_repository_key,
            reference_id,
            context,
            allowed_repositories,
            limit,
            cache_read,
        )


async def resolve_external_reference(
    conn: asyncpg.Connection,
    source_repository_key: str,
    reference_id: str,
    context: ResolverContext,
    *,
    allowed_repositories: frozenset[str],
    limit: int = 50,
) -> CandidateResolution:
    """Resolve authorized versions, reading a verified derivative cache or computing C04."""
    return await _resolve_request(
        conn,
        source_repository_key,
        reference_id,
        context,
        allowed_repositories=allowed_repositories,
        limit=limit,
        cache_read=True,
    )
