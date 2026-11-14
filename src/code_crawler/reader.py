"""Bounded typed canonical reads in a pinned published-snapshot transaction."""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

import asyncpg
from pydantic import TypeAdapter

from code_crawler.publication import _AUXILIARY, _SUBTYPES, _restore_documents
from code_crawler.source_evidence import (
    SourceFragment,
    SourceUnavailableError,
    read_source_fragment,
)
from code_crawler.ucm import (
    DataAccess,
    Entity,
    Evidence,
    Relation,
    RelationKind,
    SqlBinding,
    SqlExecute,
    SqlStatement,
)

MAX_LIMIT = 200
_CONTEXT_TOKEN = object()
_ENTITIES = TypeAdapter(tuple[Entity, ...])


def _id(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"ucm:[0-9a-f]{64}", value) is None:
        raise ValueError("invalid canonical entity ID")
    return value


@dataclass(frozen=True)
class RelationPage:
    snapshot_id: UUID
    items: tuple[Relation, ...]
    truncated: bool


@dataclass(frozen=True)
class EvidenceFragment:
    evidence: Evidence
    source: SourceFragment | None
    unavailable_reason: str | None = None


class PublishedReader:
    def __init__(
        self,
        conn: asyncpg.Connection,
        repository_id: UUID,
        snapshot_id: UUID,
        *,
        _token: object = None,
    ) -> None:
        if _token is not _CONTEXT_TOKEN:
            raise ValueError("use published_reader to select a published snapshot")
        self._conn = conn
        self._repository_id = repository_id
        self._snapshot_id = snapshot_id
        self._active = True

    @property
    def repository_id(self) -> UUID:
        return self._repository_id

    @property
    def snapshot_id(self) -> UUID:
        return self._snapshot_id

    def _check(self) -> None:
        if not self._active:
            raise ValueError("published reader context is closed")

    async def _entities(self, ids: tuple[str, ...]) -> tuple[Entity, ...]:
        self._check()
        for entity_id in ids:
            _id(entity_id)
        if not ids:
            return ()
        tables = {
            name: [] for name in ("ucm_entities", *_SUBTYPES.values(), *_AUXILIARY)
        }
        tables["ucm_entities"] = [
            dict(row)
            for row in await self._conn.fetch(
                "SELECT * FROM public.ucm_entities WHERE snapshot_id=$1 AND entity_id=ANY($2) ORDER BY entity_id",
                self.snapshot_id,
                list(ids),
            )
        ]
        if {r["entity_id"] for r in tables["ucm_entities"]} != set(ids):
            raise ValueError("entity does not exist in the selected published snapshot")
        kinds = {row["entity_type"] for row in tables["ucm_entities"]}
        for kind in kinds:
            table = _SUBTYPES.get(kind)
            if table:
                tables[table] = [
                    dict(row)
                    for row in await self._conn.fetch(
                        f"SELECT * FROM public.{table} WHERE snapshot_id=$1 AND entity_id=ANY($2)",
                        self.snapshot_id,
                        list(ids),
                    )
                ]
        for table, owner in _AUXILIARY.items():
            if table in ("ucm_sql_fragments", "ucm_sql_partial_reasons"):
                selected = [r["candidate_id"] for r in tables["ucm_sql_variants"]]
            else:
                selected = list(ids)
            if selected:
                tables[table] = [
                    dict(row)
                    for row in await self._conn.fetch(
                        f"SELECT * FROM public.{table} WHERE snapshot_id=$1 AND {owner}=ANY($2)",
                        self.snapshot_id,
                        selected,
                    )
                ]

        def hydrate() -> tuple[Entity, ...]:
            entities = _ENTITIES.validate_json(
                json.dumps(_restore_documents(tables), ensure_ascii=False)
            )
            if any(e.repository_id != str(self.repository_id) for e in entities):
                raise ValueError("entity belongs to a different repository")
            return entities

        return await asyncio.to_thread(hydrate)

    async def get_entity(self, entity_id: str) -> Entity:
        """Return a complete canonical model, including nested typed details and ranges."""
        return (await self._entities((entity_id,)))[0]

    async def get_sql_statement(self, entity_id: str) -> SqlStatement:
        entity = await self.get_entity(entity_id)
        if isinstance(entity, SqlStatement):
            return entity
        raise ValueError("entity is not a SQL statement")

    async def get_data_access(self, entity_id: str) -> DataAccess:
        entity = await self.get_entity(entity_id)
        if isinstance(entity, DataAccess):
            return entity
        raise ValueError("entity is not a data access")

    async def get_sql_binding(self, entity_id: str) -> SqlBinding:
        entity = await self.get_entity(entity_id)
        if isinstance(entity, SqlBinding):
            return entity
        raise ValueError("entity is not a SQL binding")

    async def get_sql_execute(self, entity_id: str) -> SqlExecute:
        entity = await self.get_entity(entity_id)
        if isinstance(entity, SqlExecute):
            return entity
        raise ValueError("entity is not a SQL execution")

    async def get_relations(
        self,
        entity_id: str,
        *,
        direction: str = "out",
        kinds: tuple[RelationKind, ...] = (),
        limit: int = 100,
    ) -> RelationPage:
        """Read incoming targets/candidates or outgoing source relations without promoting certainty."""
        self._check()
        _id(entity_id)
        if (
            direction not in ("in", "out")
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= MAX_LIMIT
        ):
            raise ValueError("invalid relation direction/limit")
        selected_kinds = [RelationKind(kind).value for kind in kinds]
        if not await self._conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM public.ucm_entities WHERE snapshot_id=$1 AND entity_id=$2)",
            self.snapshot_id,
            entity_id,
        ):
            raise ValueError("entity does not exist in the selected published snapshot")
        match = (
            "r.source_id=$2"
            if direction == "out"
            else "r.entity_id IN (SELECT entity_id FROM public.ucm_relations WHERE snapshot_id=$1 AND target_id=$2 UNION ALL SELECT relation_id FROM public.ucm_relation_candidates WHERE snapshot_id=$1 AND candidate_id=$2)"
        )
        rows = await self._conn.fetch(
            f"SELECT r.entity_id FROM public.ucm_relations r WHERE r.snapshot_id=$1 AND {match} AND (cardinality($3::text[])=0 OR r.relation_kind=ANY($3)) ORDER BY r.entity_id LIMIT $4",
            self.snapshot_id,
            entity_id,
            selected_kinds,
            limit + 1,
        )
        items = await self._entities(tuple(row["entity_id"] for row in rows[:limit]))
        if any(not isinstance(e, Relation) for e in items):
            raise ValueError("relation extension has wrong canonical type")
        return RelationPage(self.snapshot_id, items, len(rows) > limit)

    async def get_evidence(self, entity_id: str) -> tuple[EvidenceFragment, ...]:
        """Restore exact proofs; only historical archive absence is returned as partial."""
        entity = await self.get_entity(entity_id)
        if entity.entity_type not in ("RELATION", "EXTERNAL_REFERENCE"):
            raise ValueError("entity has no Evidence")
        results = []
        for evidence in entity.evidence:
            try:
                fragment = await read_source_fragment(
                    self._conn,
                    self.repository_id,
                    self.snapshot_id,
                    evidence.source_range,
                )
            except SourceUnavailableError as error:
                results.append(EvidenceFragment(evidence, None, str(error)))
            else:
                results.append(EvidenceFragment(evidence, fragment))
        return tuple(results)


@asynccontextmanager
async def published_reader(
    conn: asyncpg.Connection, repository_key: str
) -> AsyncIterator[PublishedReader]:
    """Pin one publication in a read-only repeatable-read transaction for a compound read."""
    if conn.is_in_transaction():
        raise ValueError("published reader requires a free connection")
    if not isinstance(repository_key, str) or not repository_key.strip():
        raise ValueError("repository key must be nonblank")
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        row = await conn.fetchrow(
            "SELECT s.repository_id,s.id FROM public.ucm_repositories r JOIN public.ucm_repository_publications p ON p.repository_id=r.id JOIN public.ucm_snapshots s ON (s.repository_id,s.id)=(p.repository_id,p.snapshot_id) WHERE r.repository_key=$1 AND s.state='PUBLISHED'",
            repository_key,
        )
        if row is None:
            raise ValueError("repository has no published snapshot")
        reader = PublishedReader(
            conn, row["repository_id"], row["id"], _token=_CONTEXT_TOKEN
        )
        try:
            yield reader
        finally:
            reader._active = False
