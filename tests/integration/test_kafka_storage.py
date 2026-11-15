import asyncio
from pathlib import Path

import asyncpg
import pytest
from test_kafka_adapter import CONFIG, JAVA, attributes, symbols

from code_crawler import db, repos, search, snapshots
from code_crawler.bpmn_adapter import BpmnSourceAdapter
from code_crawler.incremental import _capture
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.kafka_adapter import KafkaSourceAdapter
from code_crawler.publication import (
    load_snapshot_batch,
    publish_snapshot,
    validate_snapshot,
)
from code_crawler.reader import published_reader
from code_crawler.source_adapters import AdapterError, AdapterRegistry, index_sources
from code_crawler.ucm import ExternalReference, Relation, RelationKind

pytestmark = pytest.mark.integration


def test_kafka_publication_reuse_context_edit_topic_delete_and_isolation(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        conn = await asyncpg.connect(database_url)
        try:
            for migration in await db.begin_migration(conn, init=True):
                await db.apply_migration(conn, migration)
            await conn.execute("SELECT pg_advisory_unlock_all()")
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "Kafka Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            (tmp_path / "Handler.java").write_text(JAVA)
            (tmp_path / "application.properties").write_text(CONFIG)
            (tmp_path / "flow.bpmn").write_text(
                '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"><process id="p"/></definitions>'
            )

            async def commit(message):
                await repos.git("add", ".", cwd=tmp_path)
                await repos.git("commit", "-m", message, cwd=tmp_path)

            await commit("fixture")
            repo = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="kafka-a",
                    display_name="Kafka A",
                    source=str(tmp_path),
                ),
            )
            registry = AdapterRegistry(
                (
                    KafkaSourceAdapter(JavaSourceAdapter(profile="orm")),
                    BpmnSourceAdapter(),
                )
            )
            first = await index_sources(conn, repo, tmp_path, registry)
            await validate_snapshot(conn, first.snapshot_id)
            await publish_snapshot(
                conn, repo, first.snapshot_id, expected_snapshot_id=None
            )
            batch = await load_snapshot_batch(conn, first.snapshot_id)
            assert len(symbols(batch.entities, "KAFKA_CONSUMER")) == 1
            assert len(symbols(batch.entities, "KAFKA_PRODUCER")) == 2
            topics = symbols(batch.entities, "KAFKA_TOPIC")
            assert all(
                attributes(batch.entities, t)["cluster"] == "broker-a:9092"
                for t in topics
            )
            assert any(
                isinstance(e, ExternalReference)
                and e.selector.qualified_name.startswith("kafka.topic::")
                for e in batch.entities
            )
            known = next(t for t in topics if t.name == "orders")
            found = await search.search_symbols(
                conn, "kafka-a", known.qualified_name, kind="KAFKA_TOPIC"
            )
            assert known.id in {item["id"] for item in found["items"]}
            link = next(
                r
                for r in batch.entities
                if isinstance(r, Relation)
                and r.relation_kind == RelationKind.KAFKA_CONSUMES_FROM
            )
            async with published_reader(conn, "kafka-a") as view:
                proof = await view.get_evidence(link.id)
                assert len(proof) >= 2 and all(p.source is not None for p in proof)
            reuse = await index_sources(conn, repo, tmp_path, registry)
            assert reuse.plan.reanalyze == ()
            await validate_snapshot(conn, reuse.snapshot_id)
            reused = await load_snapshot_batch(conn, reuse.snapshot_id)
            assert {e.id: e for e in batch.entities} == {
                e.id: e for e in reused.entities
            }
            (tmp_path / "application.properties").write_text(
                CONFIG.replace("broker-a:9092", "broker-b:9092")
            )
            await commit("cluster edit")
            changed = await index_sources(conn, repo, tmp_path, registry)
            assert "Handler.java" in changed.plan.reanalyze
            await validate_snapshot(conn, changed.snapshot_id)
            await publish_snapshot(
                conn, repo, changed.snapshot_id, expected_snapshot_id=first.snapshot_id
            )
            updated = await load_snapshot_batch(conn, changed.snapshot_id)
            assert {t.qualified_name for t in topics}.isdisjoint(
                t.qualified_name for t in symbols(updated.entities, "KAFKA_TOPIC")
            )
            assert all(
                attributes(updated.entities, t)["cluster"] == "broker-b:9092"
                for t in symbols(updated.entities, "KAFKA_TOPIC")
            )
            captured = await _capture(tmp_path, repo, registry.languages)
            prepared = await registry.prepare(captured.sources)
            full = await prepared(
                tuple(s for s in captured.sources if registry.route(s.file.path))
            )
            full_entities = (
                *[s.file for s in captured.sources],
                *[e for analysis in full for e in analysis.entities],
            )
            assert {e.id: e for e in updated.entities} == {
                e.id: e for e in full_entities
            }
            # Registry invalidation version and configuration identity are persistent.
            from code_crawler import kafka_adapter, kafka_java

            with monkeypatch.context() as patch:
                patch.setattr(kafka_adapter, "VERSION", "kafka/test-upgrade")
                upgraded_registry = AdapterRegistry(
                    (
                        KafkaSourceAdapter(JavaSourceAdapter(profile="orm")),
                        BpmnSourceAdapter(),
                    )
                )
                upgraded = await index_sources(conn, repo, tmp_path, upgraded_registry)
                assert "Handler.java" in upgraded.plan.reanalyze
                await validate_snapshot(conn, upgraded.snapshot_id)
            other = tmp_path.with_name(tmp_path.name + "-other")
            other.mkdir()
            await repos.git("init", cwd=other)
            await repos.git("config", "user.name", "Other", cwd=other)
            await repos.git("config", "user.email", "test@example.invalid", cwd=other)
            (other / "Other.java").write_text(JAVA.replace("Handler", "Other"))
            await repos.git("add", ".", cwd=other)
            await repos.git("commit", "-m", "remote consumer", cwd=other)
            repo_b = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="kafka-b", display_name="B", source=str(other)
                ),
            )
            b = await index_sources(conn, repo_b, other, registry)
            await validate_snapshot(conn, b.snapshot_id)
            await publish_snapshot(
                conn, repo_b, b.snapshot_id, expected_snapshot_id=None
            )
            other_batch = await load_snapshot_batch(conn, b.snapshot_id)
            assert {e.id for e in batch.entities}.isdisjoint(
                e.id for e in other_batch.entities
            )
            # Deleting local consumers never creates a cross-repository canonical link.
            (tmp_path / "Handler.java").write_text(
                JAVA.replace('@KafkaListener(topics=TOPIC, groupId="orders-group")', "")
            )
            await commit("consumer deletion")
            deleted = await index_sources(conn, repo, tmp_path, registry)
            await validate_snapshot(conn, deleted.snapshot_id)
            await publish_snapshot(
                conn,
                repo,
                deleted.snapshot_id,
                expected_snapshot_id=changed.snapshot_id,
            )
            removed = await load_snapshot_batch(conn, deleted.snapshot_id)
            assert not symbols(removed.entities, "KAFKA_CONSUMER")
            assert any(
                isinstance(e, ExternalReference)
                and e.selector.qualified_name.startswith("kafka.topic::")
                for e in removed.entities
            )
            (tmp_path / "Handler.java").write_text(
                JAVA.replace('"orders"', '"new-topic"')
            )
            await commit("injected failure")

            def fail(*args, **kwargs):
                raise RuntimeError("injected Kafka detector failure")

            monkeypatch.setattr(kafka_java.Collector, "analyze", fail)
            with pytest.raises(AdapterError, match="injected Kafka detector failure"):
                await index_sources(conn, repo, tmp_path, registry)
            assert (await snapshots.published_snapshot(conn, repo))[
                "id"
            ] == deleted.snapshot_id
        finally:
            await conn.close()

    asyncio.run(run())
