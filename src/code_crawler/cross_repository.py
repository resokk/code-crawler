"""Bounded forward graph traversal with explicit, query-only external identity hops."""

import asyncio
import re
from collections import deque
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import asyncpg
from pydantic import Field

from code_crawler import discovery, external_candidates
from code_crawler.external_candidates import EvidencePath, ExternalCandidate
from code_crawler.resolver_context import ResolverContext, verify_context
from code_crawler.snapshots import pin_snapshot
from code_crawler.ucm import (
    Certainty,
    ContractModel,
    Coverage,
    EntityId,
    EntityRef,
    EntityType,
    Position,
    RelationKind,
    SourceRange,
    Text,
)

VERSION = "1"
MAX_DEPTH = 12
MAX_FANOUT = 50
MAX_NODES = 500
MAX_RESULTS = 500
MAX_REPOSITORY_HOPS = 8
MAX_TIMEOUT_MS = 30000
MAX_PROOFS = 8


class GraphLocation(ContractModel):
    repository_key: Text
    repository_id: UUID
    snapshot_id: UUID
    entity: EntityRef
    generation: UUID | None


class TraversalStep(ContractModel):
    index: int
    parent_step: int | None
    kind: Literal["LOCAL_RELATION", "EXTERNAL_IDENTITY"]
    source: GraphLocation
    target: GraphLocation | None = None
    depth: int
    repository_hops: int
    relation_id: EntityId | None = None
    relation_kind: RelationKind | None = None
    resolution: Literal["RESOLVED", "AMBIGUOUS", "PARTIAL", "UNRESOLVED"] | None
    certainty: Certainty
    coverage: Coverage
    evidence: tuple[EvidencePath, ...] = ()
    local_candidates: tuple[GraphLocation, ...] = ()
    remote_candidates: tuple[ExternalCandidate, ...] = ()
    reasons: tuple[str, ...] = ()
    assertion_scope: Literal["DECLARATION_IDENTITY"] | None = None
    followed: bool = False
    stop_reason: str | None = None
    truncated: bool = False


class TraversalLimits(ContractModel):
    depth: int
    fanout: int
    max_nodes: int
    max_repository_hops: int
    max_results: int
    timeout_ms: int


class GraphTrace(ContractModel):
    contract_version: Literal[1] = 1
    context_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    root: GraphLocation | None
    nodes: tuple[GraphLocation, ...]
    steps: tuple[TraversalStep, ...]
    limits: TraversalLimits
    expanded_nodes: int
    result_units: int
    truncated: bool
    reasons: tuple[str, ...]
    unavailable_repositories: tuple[str, ...]
    coverage: Coverage


def _key(location):
    return (location.repository_id, location.snapshot_id, location.entity.id)


def _coverage(reasons=()):
    return Coverage(
        capability="graph.cross_repository",
        analyzer_version=VERSION,
        status="PARTIAL" if reasons else "COMPLETE",
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class _Visit:
    location: GraphLocation
    depth: int
    hops: int
    parent: int | None
    ancestors: tuple


class _Walk:
    def __init__(self, context, depth, fanout, max_nodes, max_hops, max_results, kinds):
        self.context = context
        self.selections = {s.repository_key: s for s in context.selections}
        self.depth, self.fanout, self.max_nodes, self.max_hops, self.max_results = (
            depth,
            fanout,
            max_nodes,
            max_hops,
            max_results,
        )
        self.kinds = kinds
        self.root = None
        self.nodes = {}
        self.steps = []
        self.queue = deque()
        self.states = {}
        self.units = 0
        self.expanded = 0
        self.reasons = []
        self.truncated = False
        self.unavailable = ()

    def note(self, reason, cut=False):
        if reason not in self.reasons:
            self.reasons.append(reason)
        self.truncated |= cut

    def location(self, selection, entity_type, entity_id):
        return GraphLocation(
            repository_key=selection.repository_key,
            repository_id=selection.repository_id,
            snapshot_id=selection.snapshot_id,
            generation=selection.generation,
            entity=EntityRef(entity_type=EntityType(entity_type), id=entity_id),
        )

    def admit(self, location):
        key = _key(location)
        if key not in self.nodes:
            if len(self.nodes) >= self.max_nodes:
                self.note("NODE_LIMIT", True)
                return False
            self.nodes[key] = location
        return True

    def follow(self, visit, target, hops, index):
        key = _key(target)
        if key in visit.ancestors:
            return False, "CYCLE"
        depth = visit.depth + 1
        previous = self.states.setdefault(key, [])
        if any(d <= depth and h <= hops for d, h in previous):
            return False, "ALREADY_VISITED"
        previous.append((depth, hops))
        self.queue.append(_Visit(target, depth, hops, index, (*visit.ancestors, key)))
        return True, None

    def emit(self, visit, **fields):
        step = TraversalStep(
            index=len(self.steps),
            parent_step=visit.parent,
            source=visit.location,
            depth=visit.depth + 1,
            repository_hops=visit.hops,
            **fields,
        )
        self.steps.append(step)
        self.units += 1 + len(step.local_candidates) + len(step.remote_candidates)
        if step.resolution not in (None, "RESOLVED"):
            self.note("UNCERTAIN_EDGE")
        if step.coverage.status != "COMPLETE":
            self.note("PARTIAL_EDGE_COVERAGE")
        if any(not e.available for e in step.evidence):
            self.note("EVIDENCE_UNAVAILABLE")
        return step

    async def proofs(self, conn, selection, owner):
        rows = await conn.fetch(
            """
            SELECT p.*,f.path,f.content_sha256,(a.source_file_id IS NOT NULL) AS archived
            FROM public.ucm_evidence p JOIN public.ucm_source_files f
              ON f.snapshot_id=p.snapshot_id AND f.entity_id=p.source_file_id
            LEFT JOIN public.ucm_snapshot_sources a
              ON a.snapshot_id=f.snapshot_id AND a.source_file_id=f.entity_id AND a.content_sha256=f.content_sha256
            WHERE p.snapshot_id=$1 AND p.owner_id=$2 ORDER BY p.ordinal LIMIT $3
            """,
            selection.snapshot_id,
            owner,
            MAX_PROOFS + 1,
        )
        cut = len(rows) > MAX_PROOFS
        if cut:
            self.note("EVIDENCE_LIMIT", True)
        proofs = []
        for row in rows[:MAX_PROOFS]:
            proofs.append(
                EvidencePath(
                    repository_id=selection.repository_id,
                    snapshot_id=selection.snapshot_id,
                    entity_id=owner,
                    generation=selection.generation,
                    path=row["path"],
                    content_sha256=row["content_sha256"],
                    source_range=SourceRange(
                        source_file_id=row["source_file_id"],
                        start=Position(
                            line=row["start_line"], byte_column=row["start_byte_column"]
                        ),
                        end=Position(
                            line=row["end_line"], byte_column=row["end_byte_column"]
                        ),
                    ),
                    rule=row["rule"],
                    available=row["archived"],
                    unavailable_reason=None
                    if row["archived"]
                    else "source archive unavailable",
                )
            )
        return tuple(proofs), cut

    async def local(self, conn, visit):
        selection = self.selections[visit.location.repository_key]
        rows = await conn.fetch(
            "SELECT * FROM public.ucm_relations WHERE snapshot_id=$1 AND source_id=$2 "
            "AND (cardinality($3::text[])=0 OR relation_kind=ANY($3)) ORDER BY entity_id LIMIT $4",
            selection.snapshot_id,
            visit.location.entity.id,
            [k.value for k in self.kinds],
            self.fanout + 1,
        )
        if len(rows) > self.fanout:
            self.note("FANOUT_LIMIT", True)
        for row in rows[: self.fanout]:
            if self.units >= self.max_results:
                self.note("RESULT_LIMIT", True)
                return
            evidence, cut = await self.proofs(conn, selection, row["entity_id"])
            reasons = await conn.fetch(
                "SELECT reason FROM public.ucm_coverage_reasons WHERE snapshot_id=$1 AND owner_id=$2 ORDER BY ordinal LIMIT $3",
                selection.snapshot_id,
                row["entity_id"],
                MAX_PROOFS + 1,
            )
            if len(reasons) > MAX_PROOFS:
                cut = True
                self.note("COVERAGE_REASON_LIMIT", True)
            coverage = Coverage(
                capability=row["coverage_capability"],
                analyzer_version=row["coverage_analyzer_version"],
                status=row["coverage_status"],
                reasons=tuple(r["reason"] for r in reasons[:MAX_PROOFS]),
            )
            target = None
            stop = row["reason"]
            followed = False
            if row["target_id"] is not None:
                target = self.location(selection, row["target_type"], row["target_id"])
                if self.admit(target):
                    followed, stop = self.follow(
                        visit, target, visit.hops, len(self.steps)
                    )
                else:
                    target = None
                    stop = "NODE_LIMIT"
                    cut = True
            candidates = []
            if row["resolution"] in ("PARTIAL", "AMBIGUOUS"):
                budget = min(self.fanout, self.max_results - self.units - 1)
                found = await conn.fetch(
                    "SELECT candidate_id,candidate_type FROM public.ucm_relation_candidates WHERE snapshot_id=$1 AND relation_id=$2 ORDER BY candidate_id LIMIT $3",
                    selection.snapshot_id,
                    row["entity_id"],
                    budget + 1,
                )
                if len(found) > budget:
                    cut = True
                    self.note("CANDIDATE_LIMIT", True)
                for item in found[:budget]:
                    location = self.location(
                        selection, item["candidate_type"], item["candidate_id"]
                    )
                    if self.admit(location):
                        candidates.append(location)
                    else:
                        cut = True
            self.emit(
                visit,
                kind="LOCAL_RELATION",
                target=target,
                relation_id=row["entity_id"],
                relation_kind=RelationKind(row["relation_kind"]),
                resolution=row["resolution"],
                certainty=Certainty(row["certainty"]),
                coverage=coverage,
                evidence=evidence,
                local_candidates=tuple(candidates),
                followed=followed,
                stop_reason=stop,
                truncated=cut,
                reasons=(row["reason"],) if row["reason"] else (),
            )

    async def remote(self, conn, visit, grants):
        selection = self.selections[visit.location.repository_key]
        budget = min(self.fanout, self.max_results - self.units - 1)
        if visit.hops >= self.max_hops or budget < 1:
            reason = (
                "REPOSITORY_HOP_LIMIT"
                if visit.hops >= self.max_hops
                else "RESULT_LIMIT"
            )
            self.note(reason, True)
            evidence, cut = await self.proofs(conn, selection, visit.location.entity.id)
            self.emit(
                visit,
                kind="EXTERNAL_IDENTITY",
                resolution=None,
                certainty=Certainty.UNKNOWN,
                coverage=_coverage((reason,)),
                evidence=evidence,
                stop_reason=reason,
                truncated=True,
            )
            return
        resolved = await external_candidates.resolve_external_reference(
            conn,
            selection.repository_key,
            visit.location.entity.id,
            self.context,
            allowed_repositories=grants,
            limit=budget,
        )
        if resolved.truncated:
            self.note("CANDIDATE_LIMIT", True)
        candidates = []
        cut = resolved.truncated
        for candidate in resolved.candidates:
            target_selection = self.selections[candidate.repository_key]
            discovery.authorize((candidate.repository_key,), grants)
            location = self.location(
                target_selection, candidate.target.entity_type, candidate.target.id
            )
            if self.admit(location):
                candidates.append(candidate)
            else:
                cut = True
        if (
            len(resolved.source_evidence) > MAX_PROOFS
            or len(resolved.reasons) > MAX_PROOFS
        ):
            cut = True
            self.note("EVIDENCE_LIMIT", True)
        target = None
        followed = False
        stop = resolved.status if resolved.status != "RESOLVED" else None
        hops = visit.hops
        certainty = Certainty.UNKNOWN
        if resolved.status == "RESOLVED" and candidates:
            candidate = candidates[0]
            target = self.location(
                self.selections[candidate.repository_key],
                candidate.target.entity_type,
                candidate.target.id,
            )
            hops += int(target.repository_id != visit.location.repository_id)
            certainty = candidate.certainty
            followed, stop = self.follow(visit, target, hops, len(self.steps))
        elif resolved.status == "RESOLVED":
            stop = "NODE_LIMIT"
        step = self.emit(
            visit,
            kind="EXTERNAL_IDENTITY",
            target=target,
            resolution=resolved.status,
            certainty=certainty,
            coverage=resolved.coverage,
            evidence=resolved.source_evidence[:MAX_PROOFS],
            reasons=resolved.reasons[:MAX_PROOFS],
            assertion_scope="DECLARATION_IDENTITY",
            remote_candidates=tuple(candidates),
            followed=followed,
            stop_reason=stop,
            truncated=cut,
        )
        self.steps[-1] = step.model_copy(update={"repository_hops": hops})

    async def run(self, conn, source_key, entity_id, grants):
        self.unavailable = await verify_context(
            conn, self.context, allowed_repositories=grants
        )
        if self.unavailable:
            self.note("GENERATION_UNAVAILABLE")
        for selected in sorted(self.context.selections, key=lambda s: s.snapshot_id):
            await pin_snapshot(conn, selected.snapshot_id)
        source = self.selections[source_key]
        entity_type = await conn.fetchval(
            "SELECT entity_type FROM public.ucm_entities WHERE snapshot_id=$1 AND entity_id=$2",
            source.snapshot_id,
            entity_id,
        )
        if entity_type is None:
            raise ValueError(
                "start entity does not exist in the selected repository snapshot"
            )
        self.root = self.location(source, entity_type, entity_id)
        self.admit(self.root)
        self.states[_key(self.root)] = [(0, 0)]
        self.queue.append(_Visit(self.root, 0, 0, None, (_key(self.root),)))
        while self.queue:
            if self.units >= self.max_results:
                self.note("RESULT_LIMIT", True)
                break
            visit = self.queue.popleft()
            if visit.depth >= self.depth:
                self.note("DEPTH_LIMIT", True)
                continue
            self.expanded += 1
            if visit.location.entity.entity_type == EntityType.EXTERNAL_REFERENCE:
                await self.remote(conn, visit, grants)
            else:
                await self.local(conn, visit)

    def result(self):
        return GraphTrace(
            context_fingerprint=self.context.fingerprint,
            root=self.root,
            nodes=tuple(self.nodes.values()),
            steps=tuple(self.steps),
            limits=self.limits,
            expanded_nodes=self.expanded,
            result_units=self.units,
            truncated=self.truncated,
            reasons=tuple(self.reasons),
            unavailable_repositories=self.unavailable,
            coverage=_coverage(self.reasons),
        )


async def trace_cross_repository(
    conn: asyncpg.Connection,
    repository_key: str,
    entity_id: str,
    context: ResolverContext,
    *,
    allowed_repositories: frozenset[str],
    depth: int = 4,
    fanout: int = 20,
    max_nodes: int = 100,
    max_repository_hops: int = 2,
    max_results: int = 100,
    timeout_ms: int = 5000,
    relation_kinds: tuple[RelationKind, ...] = (),
) -> GraphTrace:
    """Trace exact authorized versions; unresolved candidates never become confirmed continuations."""
    context = ResolverContext.model_validate_json(context.model_dump_json())
    discovery.authorize(
        tuple(s.repository_key for s in context.selections), allowed_repositories
    )
    if repository_key not in {s.repository_key for s in context.selections}:
        raise ValueError("start repository is not selected")
    if (
        not isinstance(entity_id, str)
        or re.fullmatch(r"ucm:[0-9a-f]{64}", entity_id) is None
    ):
        raise ValueError("invalid canonical entity ID")
    for value, lo, hi in (
        (depth, 1, MAX_DEPTH),
        (fanout, 1, MAX_FANOUT),
        (max_nodes, 1, MAX_NODES),
        (max_repository_hops, 0, MAX_REPOSITORY_HOPS),
        (max_results, 1, MAX_RESULTS),
        (timeout_ms, 1, MAX_TIMEOUT_MS),
    ):
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError("invalid traversal bounds")
    kinds = tuple(RelationKind(k) for k in relation_kinds)
    walk = _Walk(
        context, depth, fanout, max_nodes, max_repository_hops, max_results, kinds
    )
    walk.limits = TraversalLimits(
        depth=depth,
        fanout=fanout,
        max_nodes=max_nodes,
        max_repository_hops=max_repository_hops,
        max_results=max_results,
        timeout_ms=timeout_ms,
    )
    nested = conn.is_in_transaction()
    if nested and (
        await conn.fetchval("SHOW transaction_isolation")
        not in ("repeatable read", "serializable")
        or await conn.fetchval("SHOW transaction_read_only") != "on"
    ):
        raise ValueError("graph traversal requires read-only repeatable read")
    try:
        async with asyncio.timeout(timeout_ms / 1000):
            transaction = (
                conn.transaction()
                if nested
                else conn.transaction(isolation="repeatable_read", readonly=True)
            )
            async with transaction:
                await walk.run(conn, repository_key, entity_id, allowed_repositories)
    except TimeoutError:
        walk.note("TIMEOUT", True)
    return walk.result()
