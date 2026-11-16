import asyncio
import hashlib
import json
from uuid import uuid4

import asyncpg
import pytest
from fastmcp.server.auth import AccessToken
from test_access import call_http, http_client
from test_data_security import TOKEN
from test_publication import setup
from test_search_documents import REPO

from code_crawler import access, repos, snapshots
from code_crawler.access import authorized_evidence
from code_crawler.data_security import (
    MARKER,
    DataSecurityError,
    SecretPolicy,
    embedding_input,
)
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.jobs import collect_garbage
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.search_storage import (
    read_search_documents,
    read_search_security_report,
    rebuild_search_documents,
)
from code_crawler.source_adapters import AdapterRegistry, index_sources
from code_crawler.source_evidence import read_source_file, read_source_fragment
from code_crawler.ucm import Relation, SourceFile

pytestmark = pytest.mark.integration


def test_source_originals_derivatives_rejection_acl_mcp_and_gc(
    database_url, tmp_path, access_policy_config, monkeypatch, caplog
):
    monkeypatch.setenv("DATABASE_URL", database_url)
    caplog.set_level("INFO", logger="code_crawler.audit")
    tokens, policy_json = access_policy_config
    text = REPO.replace("WHERE id = ?", f"WHERE id = ? AND password = '{TOKEN}'")

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await setup(conn)
            root = tmp_path / "app"
            root.mkdir()
            await repos.git("init", cwd=root)
            await repos.git("config", "user.name", "Security Test", cwd=root)
            await repos.git("config", "user.email", "test@example.invalid", cwd=root)
            (root / "Repo.java").write_text(text)
            await repos.git("add", ".", cwd=root)
            await repos.git("commit", "-m", "fixture", cwd=root)
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="app", display_name="app", source="fixture"
                ),
            )
            registry = AdapterRegistry((JavaSourceAdapter(profile="orm"),))
            indexed = await index_sources(conn, repo, root, registry)
            snapshot = indexed.snapshot_id
            await validate_snapshot(conn, snapshot)
            await publish_snapshot(conn, repo, snapshot, expected_snapshot_id=None)
            batch = await load_snapshot_batch(conn, snapshot)
            file = next(e for e in batch.entities if isinstance(e, SourceFile))
            original = await read_source_file(conn, repo, snapshot, file.id)
            assert original.content == text.encode()
            assert (
                original.provenance.content_sha256
                == hashlib.sha256(text.encode()).hexdigest()
            )
            relation = None
            for e in batch.entities:
                if not isinstance(e, Relation):
                    continue
                for ev in e.evidence:
                    source = await read_source_fragment(
                        conn, repo, snapshot, ev.source_range
                    )
                    if TOKEN.encode() in source.content:
                        relation = e
                        break
                if relation:
                    break
            assert relation is not None
            credential = AccessToken(
                token=tokens["alice"], client_id="forged", scopes=[]
            )
            fragments = await authorized_evidence(
                conn, access.load_policy(), credential, "app", relation.id
            )
            assert any(TOKEN.encode() in f.source.content for f in fragments)
            with pytest.raises(PermissionError):
                await authorized_evidence(
                    conn, access.load_policy(), credential, "other", relation.id
                )
            restricted = access.AccessPolicy.model_validate_json(
                json.dumps(
                    {
                        "principals": [
                            {**policy_json["principals"][0], "permissions": ["read"]}
                        ]
                    }
                )
            )
            with pytest.raises(PermissionError):
                await authorized_evidence(
                    conn, restricted, credential, "app", relation.id
                )

            async def build(expected, action="mask"):
                return await rebuild_search_documents(
                    conn,
                    repo,
                    snapshot,
                    allowed_repository_ids=[repo],
                    policy_version="fixture-v1",
                    redact=str,
                    expected_generation_id=expected,
                    security_policy=SecretPolicy(action),
                )

            first = await build(None)
            docs = await read_search_documents(
                conn, repo, allowed_repository_ids=[repo]
            )
            encoded = json.dumps(docs, default=str)
            assert TOKEN not in encoded and MARKER in encoded
            report = await read_search_security_report(
                conn, repo, allowed_repository_ids=[repo]
            )
            assert report["status"] == "PARTIAL" and report["redacted_documents"] > 0
            assert all(TOKEN not in embedding_input(d["content"]) for d in docs)
            for api in (read_search_documents, read_search_security_report):
                with pytest.raises(PermissionError):
                    await api(conn, repo, allowed_repository_ids=[])
            with pytest.raises(DataSecurityError, match="rejected"):
                await build(first, "reject")
            assert (
                await conn.fetchval(
                    "SELECT generation_id FROM search_index_publications WHERE snapshot_id=$1",
                    snapshot,
                )
                == first
            )
            assert (
                await read_search_documents(conn, repo, allowed_repository_ids=[repo])
                == docs
            )
            second = await build(first)
            rebuilt = await read_search_documents(
                conn, repo, allowed_repository_ids=[repo]
            )
            assert [(d["document_id"], d["content_sha256"]) for d in rebuilt] == [
                (d["document_id"], d["content_sha256"]) for d in docs
            ]
            await build(second, "skip")
            skip_report = await read_search_security_report(
                conn, repo, allowed_repository_ids=[repo]
            )
            assert (
                skip_report["skipped_documents"] > 0
                and skip_report["status"] == "PARTIAL"
            )
            assert TOKEN not in json.dumps(skip_report)
            with pytest.raises(asyncpg.CheckViolationError, match="immutable"):
                await conn.execute(
                    "UPDATE search_index_generations SET security_report='{}' WHERE id=$1",
                    first,
                )
            legacy = uuid4()
            current = await conn.fetchval(
                "SELECT generation_id FROM search_index_publications WHERE snapshot_id=$1",
                snapshot,
            )
            await conn.execute(
                "INSERT INTO search_index_generations(id,repository_id,snapshot_id,projection_version,policy_version,document_count) VALUES($1,$2,$3,'search-documents-v1','legacy',0)",
                legacy,
                repo,
                snapshot,
            )
            await conn.execute(
                "UPDATE search_index_generations SET sealed=true WHERE id=$1", legacy
            )
            await conn.execute(
                "UPDATE search_index_publications SET generation_id=$1 WHERE snapshot_id=$2",
                legacy,
                snapshot,
            )
            with pytest.raises(LookupError, match="rebuild required"):
                await read_search_documents(conn, repo, allowed_repository_ids=[repo])
            await conn.execute(
                "UPDATE search_index_publications SET generation_id=$1 WHERE snapshot_id=$2",
                current,
                snapshot,
            )
            async with http_client() as client:
                result = await call_http(
                    client,
                    tokens["alice"],
                    "find_sql_executions",
                    {"repository_key": "app"},
                )
                assert not result.json()["result"].get("isError"), result.text
                assert TOKEN not in result.text and MARKER in result.text
                assert (
                    result.json()["result"]["structuredContent"]["data_security"][
                        "status"
                    ]
                    == "PARTIAL"
                )
                denied = await call_http(
                    client,
                    tokens["bob"],
                    "get_evidence",
                    {"repository_key": "app", "relation_id": relation.id},
                )
                assert "access denied" in denied.text and TOKEN not in denied.text
            (root / "Repo.java").unlink()
            assert (
                await read_source_file(conn, repo, snapshot, file.id)
            ).content == text.encode()
            (root / "Repo.java").write_text(text)
            replacement = await index_sources(conn, repo, root, registry)
            await validate_snapshot(conn, replacement.snapshot_id)
            await publish_snapshot(
                conn, repo, replacement.snapshot_id, expected_snapshot_id=snapshot
            )
            collected = await collect_garbage(conn, keep_retired=0)
            assert snapshot in collected["retired"]
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM search_documents WHERE snapshot_id=$1",
                    snapshot,
                )
                == 0
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM search_index_generations WHERE snapshot_id=$1",
                    snapshot,
                )
                == 0
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_source_blobs WHERE repository_id=$1", repo
                )
                > 0
            )
            assert (
                await read_source_file(conn, repo, replacement.snapshot_id, file.id)
            ).content == text.encode()
        finally:
            await conn.close()

    asyncio.run(run())
    assert TOKEN not in caplog.text
