"""Reversible legacy/UCM compatibility migration and persistent read routing."""

import asyncio
import json
from pathlib import Path
from uuid import UUID

import asyncpg

from code_crawler import indexer, snapshots
from code_crawler.incremental import _capture, _Worktree
from code_crawler.ingestion import UcmBatch, _ingest_records, _records
from code_crawler.publication import publish_snapshot, validate_snapshot
from code_crawler.ucm import (
    Certainty,
    CodeEntity,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    Position,
    Relation,
    RelationKind,
    Resolution,
    SourceRange,
    logical_id,
    relation_registry,
)

LIMITATIONS = (
    "compatibility identity is not overload identity",
    "legacy executes/data accesses are preserved only in compatibility projection",
    "Java/SQL and PLPlus coverage is incomplete; canonical semantic adapters are pending",
)


def _payload(graph: indexer.Graph) -> str:
    return json.dumps(
        {
            "nodes": graph.nodes,
            "edges": sorted(
                graph.edges, key=lambda row: json.dumps(row, sort_keys=True)
            ),
            "refs": sorted(graph.refs, key=lambda row: json.dumps(row, sort_keys=True)),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


async def _legacy_graph(conn: asyncpg.Connection, repo_id: int) -> indexer.Graph:
    nodes = await conn.fetch(
        "SELECT * FROM nodes WHERE repo_id=$1 ORDER BY id", repo_id
    )
    ids = {row["id"]: i for i, row in enumerate(nodes)}
    graph = indexer.Graph(
        nodes=[
            (
                r["kind"],
                r["name"],
                r["qualified_name"],
                r["file_path"],
                r["start_line"],
                r["end_line"],
                json.loads(r["attrs"]),
            )
            for r in nodes
        ]
    )
    graph.edges = [
        (ids[r["src_id"]], ids[r["dst_id"]], r["kind"], json.loads(r["attrs"]))
        for r in await conn.fetch(
            "SELECT e.* FROM edges e JOIN nodes n ON n.id=e.src_id WHERE n.repo_id=$1",
            repo_id,
        )
    ]
    graph.refs = [
        (
            ids[r["node_id"]],
            r["kind"],
            r["table_name"],
            r["column_name"],
            json.loads(r["attrs"]),
        )
        for r in await conn.fetch(
            "SELECT r.* FROM data_refs r JOIN nodes n ON n.id=r.node_id WHERE n.repo_id=$1",
            repo_id,
        )
    ]
    return graph


async def _projection(
    conn: asyncpg.Connection, snap: UUID, legacy_id: int
) -> indexer.Graph:
    header = await conn.fetchrow(
        "SELECT * FROM ingest_legacy_snapshots WHERE snapshot_id=$1", snap
    )
    if header is None or header["legacy_repo_id"] != legacy_id:
        raise ValueError("published snapshot has no matching compatibility projection")
    rows = {}
    for table, count in (
        ("ingest_legacy_nodes", "node_count"),
        ("ingest_legacy_edges", "edge_count"),
        ("ingest_legacy_refs", "ref_count"),
    ):
        rows[table] = await conn.fetch(
            f"SELECT * FROM {table} WHERE snapshot_id=$1 ORDER BY ordinal", snap
        )
        if len(rows[table]) != header[count] or [
            r["ordinal"] for r in rows[table]
        ] != list(range(header[count])):
            raise ValueError("incomplete compatibility projection")
    return indexer.Graph(
        nodes=[
            (
                r["kind"],
                r["name"],
                r["qualified_name"],
                r["file_path"],
                r["start_line"],
                r["end_line"],
                json.loads(r["attrs"]),
            )
            for r in rows["ingest_legacy_nodes"]
        ],
        edges=[
            (r["src"], r["dst"], r["kind"], json.loads(r["attrs"]))
            for r in rows["ingest_legacy_edges"]
        ],
        refs=[
            (
                r["node"],
                r["kind"],
                r["table_name"],
                r["column_name"],
                json.loads(r["attrs"]),
            )
            for r in rows["ingest_legacy_refs"]
        ],
    )


def _convert(
    repo: UUID, captured: _Worktree, graph: indexer.Graph
) -> tuple[UcmBatch, list[str]]:
    files = {source.file.path: source for source in captured.sources}
    entities = [source.file for source in captured.sources]
    ids = []
    types = []
    for ordinal, node in enumerate(graph.nodes):
        kind, name, qualified, path, *_ = node
        if kind == "file":
            if path not in files:
                raise ValueError("legacy file not present in captured sources")
            entity = files[path].file
        else:
            entity_type = {
                "class": EntityType.CLASS,
                "method": EntityType.METHOD,
                "function": EntityType.METHOD,
                "sql_query": EntityType.SQL_CANDIDATE,
            }.get(kind)
            if entity_type is None:
                raise ValueError(f"unsupported legacy node kind: {kind}")
            key = json.dumps(
                ["legacy", kind, path, qualified, ordinal],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            entity = CodeEntity(
                repository_id=str(repo),
                logical_key=key,
                name=name,
                id=logical_id(str(repo), entity_type, key),
                entity_type=entity_type,
            )
            entities.append(entity)
        ids.append(entity.id)
        types.append(entity.entity_type)
    for ordinal, (src, dst, kind, _) in enumerate(graph.edges):
        if (
            kind != "contains"
            or (types[src], types[dst])
            not in relation_registry()[RelationKind.CONTAINS]
        ):
            continue
        path = next(
            (graph.nodes[i][3] for i in (src, dst) if graph.nodes[i][3] in files), None
        )
        if path is None:
            continue
        source = files[path]
        lines = source.content.split(b"\n")
        location = SourceRange(
            source_file_id=source.file.id,
            start=Position(line=1, byte_column=0),
            end=Position(line=len(lines), byte_column=len(lines[-1])),
        )
        key = f"legacy-contains:{ordinal}"
        entities.append(
            Relation(
                repository_id=str(repo),
                logical_key=key,
                name="contains",
                id=logical_id(str(repo), EntityType.RELATION, key),
                relation_kind=RelationKind.CONTAINS,
                source=EntityRef(id=ids[src], entity_type=types[src]),
                resolution=Resolution(
                    status="RESOLVED",
                    target=EntityRef(id=ids[dst], entity_type=types[dst]),
                ),
                certainty=Certainty.INFERRED,
                evidence=(
                    Evidence(
                        source_range=location,
                        analyzer="legacy-bridge",
                        analyzer_version="1",
                        rule="legacy.contains",
                        description="Existing analyzer containment; file-level evidence",
                    ),
                ),
                coverage=Coverage(
                    capability="legacy.structure",
                    analyzer_version="1",
                    status="PARTIAL",
                    reasons=LIMITATIONS,
                ),
            )
        )
    return UcmBatch(repository_id=repo, entities=tuple(entities)), ids


def _free(conn: asyncpg.Connection) -> None:
    if conn.is_in_transaction():
        raise ValueError("legacy migration API requires a free connection")


async def migrate_index(
    conn: asyncpg.Connection, legacy_name: str, repository_key: str
) -> UUID:
    """Publish a compatible UCM snapshot without changing legacy rows or read backend."""
    _free(conn)
    async with conn.transaction(isolation="repeatable_read"):
        legacy = await conn.fetchrow("SELECT * FROM repos WHERE name=$1", legacy_name)
        if legacy is None or legacy["indexed_at"] is None:
            raise ValueError("legacy index does not exist")
        graph = await _legacy_graph(conn, legacy["id"])
    repo = await snapshots.register_repository(
        conn,
        snapshots.RepositoryInput(
            repository_key=repository_key,
            display_name=legacy_name,
            source=legacy["source"],
        ),
    )
    await conn.execute(
        "INSERT INTO ucm_legacy_repositories(repository_id,legacy_repo_id) VALUES ($1,$2) ON CONFLICT(repository_id) DO NOTHING",
        repo,
        legacy["id"],
    )
    if (
        await conn.fetchval(
            "SELECT legacy_repo_id FROM ucm_legacy_repositories WHERE repository_id=$1",
            repo,
        )
        != legacy["id"]
    ):
        raise ValueError(
            "repository key is already linked to another legacy repository"
        )
    previous = await snapshots.published_snapshot(conn, repo)
    root = await asyncio.to_thread(Path(legacy["path"]).resolve, strict=True)
    captured = await _capture(root, repo, {".java": "java", ".plp": "plplus"})
    if captured.commit != legacy["commit_hash"]:
        raise ValueError("legacy commit differs from current checkout; run index first")
    rebuilt = await asyncio.to_thread(
        indexer.build_sources,
        [
            (s.file.path, s.content)
            for s in captured.sources
            if indexer.is_indexable(s.file.path)
        ],
    )
    if _payload(rebuilt) != _payload(graph):
        raise ValueError("legacy graph differs from captured sources; run index first")
    batch, ids = await asyncio.to_thread(_convert, repo, captured, graph)
    verified = await _capture(root, repo, {".java": "java", ".plp": "plplus"})
    if (captured.commit, captured.branch, captured.dirty, captured.fingerprint) != (
        verified.commit,
        verified.branch,
        verified.dirty,
        verified.fingerprint,
    ):
        raise ValueError("worktree changed during migration")
    snap = await snapshots.create_snapshot(
        conn,
        repo,
        snapshots.SnapshotInput(
            commit_hash=captured.commit,
            branch=captured.branch,
            source_fingerprint=captured.fingerprint,
            dirty=captured.dirty,
        ),
    )
    records = await asyncio.to_thread(_records, snap, batch)
    async with conn.transaction():
        await _ingest_records(conn, snap, repo, records)
        await conn.copy_records_to_table(
            "ingest_legacy_nodes",
            schema_name="public",
            columns=(
                "snapshot_id",
                "ordinal",
                "entity_id",
                "kind",
                "name",
                "qualified_name",
                "file_path",
                "start_line",
                "end_line",
                "attrs",
            ),
            records=[
                (snap, i, ids[i], *node[:-1], json.dumps(node[-1], ensure_ascii=False))
                for i, node in enumerate(graph.nodes)
            ],
        )
        await conn.copy_records_to_table(
            "ingest_legacy_edges",
            schema_name="public",
            columns=("snapshot_id", "ordinal", "src", "dst", "kind", "attrs"),
            records=[
                (snap, i, src, dst, kind, json.dumps(attrs, ensure_ascii=False))
                for i, (src, dst, kind, attrs) in enumerate(graph.edges)
            ],
        )
        await conn.copy_records_to_table(
            "ingest_legacy_refs",
            schema_name="public",
            columns=(
                "snapshot_id",
                "ordinal",
                "node",
                "kind",
                "table_name",
                "column_name",
                "attrs",
            ),
            records=[
                (
                    snap,
                    i,
                    node,
                    kind,
                    table,
                    column,
                    json.dumps(attrs, ensure_ascii=False),
                )
                for i, (node, kind, table, column, attrs) in enumerate(graph.refs)
            ],
        )
        await conn.execute(
            "INSERT INTO ingest_legacy_snapshots(snapshot_id,legacy_repo_id,node_count,edge_count,ref_count) VALUES ($1,$2,$3,$4,$5)",
            snap,
            legacy["id"],
            len(graph.nodes),
            len(graph.edges),
            len(graph.refs),
        )
    await validate_snapshot(conn, snap)
    await publish_snapshot(
        conn, repo, snap, expected_snapshot_id=previous["id"] if previous else None
    )
    return snap


async def _mapping(conn: asyncpg.Connection, key: str) -> asyncpg.Record:
    row = await conn.fetchrow(
        "SELECT m.* FROM ucm_legacy_repositories m JOIN ucm_repositories r ON r.id=m.repository_id WHERE r.repository_key=$1",
        key,
    )
    if row is None:
        raise ValueError("repository has no legacy migration mapping")
    return row


async def _compare(conn: asyncpg.Connection, mapping: asyncpg.Record) -> dict:
    snapshot = await snapshots.published_snapshot(conn, mapping["repository_id"])
    if snapshot is None:
        raise ValueError("repository has no published snapshot")
    legacy = await conn.fetchrow(
        "SELECT * FROM repos WHERE id=$1 FOR SHARE", mapping["legacy_repo_id"]
    )
    old = await _legacy_graph(conn, mapping["legacy_repo_id"])
    new = await _projection(conn, snapshot["id"], mapping["legacy_repo_id"])
    return {
        "matches": legacy["commit_hash"] == snapshot["commit_hash"]
        and _payload(old) == _payload(new),
        "snapshot_id": str(snapshot["id"]),
        "legacy_nodes": len(old.nodes),
        "ucm_nodes": len(new.nodes),
        "legacy_edges": len(old.edges),
        "ucm_edges": len(new.edges),
        "legacy_refs": len(old.refs),
        "ucm_refs": len(new.refs),
        "commit_matches": legacy["commit_hash"] == snapshot["commit_hash"],
        "limitations": list(LIMITATIONS),
    }


async def compare_index(conn: asyncpg.Connection, repository_key: str) -> dict:
    """Compare full compatibility graph and commit against the active legacy index."""
    _free(conn)
    async with conn.transaction(isolation="repeatable_read"):
        return await _compare(conn, await _mapping(conn, repository_key))


async def use_index(
    conn: asyncpg.Connection, repository_key: str, backend: str
) -> None:
    """Select a persistent read backend; UCM requires a successful compatibility comparison."""
    _free(conn)
    if backend not in ("legacy", "ucm"):
        raise ValueError("unknown read backend")
    async with conn.transaction():
        mapping = await _mapping(conn, repository_key)
        await conn.fetchrow(
            "SELECT id FROM ucm_repositories WHERE id=$1 FOR UPDATE",
            mapping["repository_id"],
        )
        await conn.fetchrow(
            "SELECT * FROM ucm_legacy_repositories WHERE repository_id=$1 FOR UPDATE",
            mapping["repository_id"],
        )
        if backend == "ucm" and not (await _compare(conn, mapping))["matches"]:
            raise ValueError("indices differ; read switch rejected")
        await conn.execute(
            "UPDATE ucm_legacy_repositories SET read_backend=$2 WHERE repository_id=$1",
            mapping["repository_id"],
            backend,
        )


async def read_graph(conn: asyncpg.Connection, repository_key: str) -> indexer.Graph:
    """Read selected backend in one consistent transaction; no session state or writes."""
    _free(conn)
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        mapping = await _mapping(conn, repository_key)
        if mapping["read_backend"] == "legacy":
            return await _legacy_graph(conn, mapping["legacy_repo_id"])
        snapshot = await snapshots.published_snapshot(conn, mapping["repository_id"])
        if snapshot is None:
            raise ValueError("no published UCM snapshot")
        return await _projection(conn, snapshot["id"], mapping["legacy_repo_id"])
