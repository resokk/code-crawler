import asyncio
import json
from uuid import uuid4

import asyncpg
import pytest

from code_crawler import db, publication, repos, snapshots, source_evidence
from code_crawler import observability as metrics
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.source_adapters import AdapterRegistry, index_sources

pytestmark = pytest.mark.integration


def test_monitoring_pipeline_is_scoped_redacted_and_independent(database_url, tmp_path):
    async def run():
        conn = await asyncpg.connect(database_url)
        other = await asyncpg.connect(database_url)
        try:
            for name in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, name)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            ids = []
            roots = []
            for key in ("one", "two"):
                root = tmp_path / key
                root.mkdir()
                await repos.git("init", cwd=root)
                await repos.git(
                    "config", "user.email", "test@example.invalid", cwd=root
                )
                await repos.git("config", "user.name", "Test", cwd=root)
                (root / "A.java").write_text(
                    "import java.sql.*; class A { void run(Connection c,String q) throws Exception {c.prepareStatement(q).execute();} }"
                )
                await repos.git("add", ".", cwd=root)
                await repos.git("commit", "-m", "fixture", cwd=root)
                roots.append(root)
                ids.append(
                    await snapshots.register_repository(
                        conn,
                        snapshots.RepositoryInput(
                            repository_key=key, display_name=key, source=str(root)
                        ),
                    )
                )

            async with conn.transaction(isolation="repeatable_read", readonly=True):
                absent = await metrics.report(conn, "one")
            assert absent["coverage"]["status"] == "NO_PUBLICATION"
            assert absent["metrics"] == []

            async def build(connection, repo, root, attempt):
                async with metrics.recording(connection, (repo,), uuid4(), attempt):
                    result = await index_sources(
                        connection,
                        repo,
                        root,
                        AdapterRegistry((JavaSourceAdapter(profile="sql"),)),
                    )
                    await publication.validate_snapshot(connection, result.snapshot_id)
                    await publication.publish_snapshot(
                        connection, repo, result.snapshot_id, expected_snapshot_id=None
                    )
                return result

            first, second = await asyncio.gather(
                build(conn, ids[0], roots[0], 2), build(other, ids[1], roots[1], 1)
            )
            async with metrics.recording(conn, (ids[0],)):
                with metrics.span("search"):
                    metrics.response(
                        {"items": [{"source": "password=secret"}], "truncated": True}
                    )
                    metrics.cache("HIT")
                    metrics.cache("MISS")
            with pytest.raises(ValueError, match="private"):
                async with metrics.recording(conn, (ids[0],)):
                    with metrics.span("index"):
                        raise ValueError("private/source password=secret")
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                one = await metrics.report(conn, "one")
                two = await metrics.report(conn, "two")
            stages = {r["stage"]: r for r in one["metrics"]}
            assert {
                "index",
                "prepare",
                "analyze",
                "stage",
                "transfer",
                "fk",
                "validate",
                "publish",
                "db",
                "search",
            } <= stages.keys()
            assert (
                stages["index"]["errors"] == 1 and stages["index"]["max_attempt"] == 2
            )
            assert stages["stage"]["rows"] > 0
            assert stages["search"]["truncated"] == 1
            assert (
                stages["search"]["rows"]
                == stages["search"]["cache_hits"]
                == stages["search"]["cache_misses"]
                == 1
            )
            assert stages["index"]["p95_seconds"] >= stages["index"]["p50_seconds"] >= 0
            assert all(
                row["errors"] == 0 and row["max_attempt"] == 1 for row in two["metrics"]
            )
            assert one["coverage"]["snapshot_id"] == str(first.snapshot_id)
            assert two["coverage"]["snapshot_id"] == str(second.snapshot_id)
            assert any(g["status"] == "PARTIAL" for g in one["coverage"]["groups"])
            assert one["coverage"]["reported_capabilities"] > 0
            assert "secret" not in json.dumps(one) and "A.java" not in json.dumps(one)
            assert one["coverage"]["reason_categories"]
            assert one["coverage"]["adapters"][0]["files"] == 1
            job_id = await conn.fetchval(
                "SELECT job_id FROM operational_observations WHERE repository_id=$1 AND job_id IS NOT NULL LIMIT 1",
                ids[0],
            )
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                selected_job = await metrics.report(conn, "one", job_id=job_id)
                foreign_job = await metrics.report(conn, "two", job_id=job_id)
            assert foreign_job["metrics"] == []
            assert (
                next(row for row in selected_job["metrics"] if row["stage"] == "index")[
                    "errors"
                ]
                == 0
            )
            before_lock = await conn.fetchval(
                "SELECT count(*) FROM operational_observations"
            )
            async with other.transaction():
                await other.execute(
                    "LOCK TABLE operational_observations IN ACCESS EXCLUSIVE MODE"
                )
                async with metrics.recording(conn, (ids[0],)):
                    with metrics.span("search"):
                        pass
                assert not conn.is_in_transaction()
                assert (
                    await conn.fetchval(
                        "SELECT snapshot_id FROM ucm_repository_publications WHERE repository_id=$1",
                        ids[0],
                    )
                    == first.snapshot_id
                )
            assert (
                await conn.fetchval("SELECT count(*) FROM operational_observations")
                == before_lock
            )
            # Failed observation insertion cannot poison a canonical publication or its evidence.
            await conn.execute(
                "ALTER TABLE operational_observations ADD CONSTRAINT reject_metrics CHECK (false) NOT VALID"
            )
            async with metrics.recording(conn, (ids[0],)):
                with metrics.span("search"):
                    pass
            assert (
                await conn.fetchval(
                    "SELECT snapshot_id FROM ucm_repository_publications WHERE repository_id=$1",
                    ids[0],
                )
                == first.snapshot_id
            )
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM ucm_source_files WHERE snapshot_id=$1",
                    first.snapshot_id,
                )
                == 1
            )
            file_id = await conn.fetchval(
                "SELECT entity_id FROM ucm_source_files WHERE snapshot_id=$1",
                first.snapshot_id,
            )
            archived = await source_evidence.read_source_file(
                conn, ids[0], first.snapshot_id, file_id
            )
            assert archived.content == (roots[0] / "A.java").read_bytes()
            assert (
                await conn.fetchval(
                    "SELECT snapshot_id FROM ucm_repository_publications WHERE repository_id=$1",
                    ids[1],
                )
                == second.snapshot_id
            )
        finally:
            await other.close()
            await conn.close()

    asyncio.run(run())
