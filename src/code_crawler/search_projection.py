"""Bounded canonical neighborhoods for the unchanged search document formatter."""

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

import asyncpg

from code_crawler.publication import _fetch, _parse
from code_crawler.ucm import Entity, Relation, RelationKind, SqlExecute

_PAGE_SIZE = 128
_CONTEXT_LIMIT = 8192


class ProjectionBudgetError(ValueError):
    """A complete document context cannot fit the bounded projection workspace."""


_KINDS = ("SYMBOL", "SQL_STATEMENT", "DATABASE_OBJECT", "ORM_MAPPING", "ORM_QUERY")


async def _entities(
    conn: asyncpg.Connection, snapshot: UUID, ids: list[str]
) -> tuple[Entity, ...]:
    # Even a bounded neighborhood is hydrated in small canonical row pages.
    result = []
    for start in range(0, len(ids), _PAGE_SIZE):
        result.extend(
            await asyncio.to_thread(
                _parse, await _fetch(conn, snapshot, ids[start : start + _PAGE_SIZE])
            )
        )
    if {e.id for e in result} != set(ids):
        raise ValueError("missing canonical search projection context")
    return tuple(result)


async def _neighborhood(
    conn: asyncpg.Connection, snapshot: UUID, ids: list[str]
) -> tuple[Entity, ...]:
    facts = {entity.id: entity for entity in await _entities(conn, snapshot, ids)}

    async def add(keys: list[str]) -> None:
        keys = sorted(set(keys) - facts.keys())
        if len(facts) + len(keys) > _CONTEXT_LIMIT:
            raise ProjectionBudgetError("search projection context exceeds fact budget")
        facts.update((e.id, e) for e in await _entities(conn, snapshot, keys))

    # UNION uses existing source/target/candidate indexes and deduplicates self-links.
    after = ""
    while True:
        rows = await conn.fetch(
            "SELECT entity_id FROM ("
            " SELECT entity_id FROM ucm_relations WHERE snapshot_id=$1 AND source_id=ANY($2)"
            " UNION SELECT entity_id FROM ucm_relations WHERE snapshot_id=$1 AND target_id=ANY($2)"
            " UNION SELECT relation_id FROM ucm_relation_candidates WHERE snapshot_id=$1 AND candidate_id=ANY($2)"
            ") r WHERE entity_id>$3 ORDER BY entity_id LIMIT $4",
            snapshot,
            ids,
            after,
            _PAGE_SIZE,
        )
        if not rows:
            break
        await add([row["entity_id"] for row in rows])
        after = rows[-1]["entity_id"]

    after = ""
    while True:
        rows = await conn.fetch(
            "SELECT entity_id FROM ucm_data_accesses WHERE snapshot_id=$1 "
            "AND statement_id=ANY($2) AND entity_id>$3 ORDER BY entity_id LIMIT $4",
            snapshot,
            ids,
            after,
            _PAGE_SIZE,
        )
        if not rows:
            break
        await add([row["entity_id"] for row in rows])
        after = rows[-1]["entity_id"]

    neighbors = set()
    for entity in facts.values():
        if isinstance(entity, Relation):
            target = entity.resolution.target
            if entity.relation_kind == RelationKind.CALLS:
                neighbors.add(entity.source.id)
                if target:
                    neighbors.add(target.id)
            elif (
                entity.relation_kind == RelationKind.EXECUTES_STATEMENT
                and target
                and target.id in ids
            ):
                neighbors.add(entity.source.id)
    await add(sorted(neighbors))
    await add(
        sorted({e.owner_symbol_id for e in facts.values() if isinstance(e, SqlExecute)})
    )
    await add(
        sorted(
            {
                facts[key].source_range.source_file_id
                for key in ids
                if facts[key].source_range
            }
        )
    )
    return tuple(facts.values())


async def _bounded_pages(
    conn: asyncpg.Connection, snapshot: UUID, ids: list[str]
) -> AsyncIterator[tuple[list[str], tuple[Entity, ...]]]:
    oversized = False
    try:
        context = await _neighborhood(conn, snapshot, ids)
    except ProjectionBudgetError:
        oversized = True
    if oversized:
        if len(ids) == 1:
            raise ProjectionBudgetError("search document context exceeds fact budget")
        middle = len(ids) // 2
        for part in (ids[:middle], ids[middle:]):
            async for page in _bounded_pages(conn, snapshot, part):
                yield page
    else:
        yield ids, context


async def projection_pages(
    conn: asyncpg.Connection, snapshot: UUID
) -> AsyncIterator[tuple[list[str], tuple[Entity, ...]]]:
    """Yield root IDs plus complete bounded formatting/provenance context.

    Exceeding a context budget fails closed; relations and candidates are never
    truncated or silently dropped. The caller holds the immutable snapshot lease.
    """
    after = ""
    while True:
        rows = await conn.fetch(
            "SELECT e.entity_id FROM ucm_entities e LEFT JOIN ucm_symbols s "
            "ON s.snapshot_id=e.snapshot_id AND s.entity_id=e.entity_id "
            "WHERE e.snapshot_id=$1 AND e.entity_id>$2 AND e.entity_type=ANY($3) "
            "AND (e.entity_type<>'SYMBOL' OR s.symbol_kind IS NULL OR s.symbol_kind NOT IN ('PARAMETER','LOCAL_VARIABLE')) "
            "ORDER BY e.entity_id LIMIT $4",
            snapshot,
            after,
            list(_KINDS),
            _PAGE_SIZE,
        )
        if not rows:
            break
        ids = [row["entity_id"] for row in rows]
        async for page in _bounded_pages(conn, snapshot, ids):
            yield page
        after = ids[-1]
