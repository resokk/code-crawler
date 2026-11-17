"""C10/C11: source declarations, selected versions and conservative query-time matches."""

import asyncio

import asyncpg
import pytest
from test_bpmn_java_bindings import bpmn
from test_discovery_catalog_extended import migrate, publish, repository, source

from code_crawler import discovery, resolver_cache, search, snapshots
from code_crawler.bpmn_adapter import BpmnSourceAdapter
from code_crawler.ingestion import UcmBatch, ingest_batch
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.kafka_adapter import KafkaSourceAdapter
from code_crawler.publication import rollback_publication
from code_crawler.resolver_context import SnapshotPin, select_context
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.source_evidence import archive_sources
from code_crawler.ucm import ExternalReference, Relation, RelationKind, Symbol

pytestmark = pytest.mark.integration
KAFKA_SEND = """import org.springframework.kafka.core.KafkaTemplate;
class Sender { KafkaTemplate<String,String> kafka;
void send(String value) { kafka.send("payments", value); } }"""
KAFKA_DECLARE = """import org.apache.kafka.clients.admin.NewTopic;
class Topics { Object topic() { return new NewTopic("payments", 1, (short)1); } }"""
WORKER = """import io.camunda.spring.client.annotation.JobWorker;
class Worker { @JobWorker(type="accounting") void handle() {} }"""
TASK = bpmn(
    '<serviceTask id="task"><extensionElements><z:taskDefinition type="accounting"/></extensionElements></serviceTask>'
)


async def stage(conn, repo, kind, java, *, xml=None, config=None):
    registry = AdapterRegistry(
        (
            KafkaSourceAdapter(JavaSourceAdapter(profile="symbols"))
            if kind == "KAFKA_TOPIC"
            else JavaSourceAdapter(profile="symbols"),
            BpmnSourceAdapter(),
        )
    )
    sources = [source(repo, "Code.java", java, "java")]
    if xml:
        sources.append(source(repo, "flow.bpmn", xml, "bpmn"))
    if config:
        sources.append(source(repo, "application.properties", config, "properties"))
    prepared = await registry.prepare(tuple(sources))
    results = await prepared(tuple(sources))
    facts = tuple(e for result in results for e in result.entities)
    sid = await snapshots.create_snapshot(
        conn,
        repo,
        snapshots.SnapshotInput(
            commit_hash="fixture", source_fingerprint="a" * 64, dirty=False
        ),
    )
    await ingest_batch(
        conn,
        sid,
        UcmBatch(repository_id=repo, entities=(*(s.file for s in sources), *facts)),
    )
    await archive_sources(conn, sid, tuple(sources), origin="PROVIDED_BYTES")
    return sid, facts


@pytest.mark.parametrize("kind", ["KAFKA_TOPIC", "BPMN_WORKER"])
def test_resource_declarations_versions_cache_ambiguity_and_authorization(
    database_url, kind
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            repos = {
                key: await repository(conn, key)
                for key in ("source", "target", "other")
            }
            key = "payments" if kind == "KAFKA_TOPIC" else "accounting"
            sender = KAFKA_SEND if kind == "KAFKA_TOPIC" else "class Caller {}"
            declaration = KAFKA_DECLARE if kind == "KAFKA_TOPIC" else WORKER
            source_id, source_facts = await stage(
                conn,
                repos["source"],
                kind,
                sender,
                xml=TASK if kind == "BPMN_WORKER" else None,
            )
            target_id, facts = await stage(conn, repos["target"], kind, declaration)
            other_id, _ = await stage(
                conn,
                repos["other"],
                kind,
                declaration.replace("class Worker", "class Other"),
            )
            for repo_key, sid in (
                ("source", source_id),
                ("target", target_id),
                ("other", other_id),
            ):
                await publish(conn, repos[repo_key], sid)
            grants = frozenset(repos)
            refs = [
                f
                for f in source_facts
                if isinstance(f, ExternalReference)
                and f.selector.qualified_name.startswith(
                    "kafka.topic::" if kind == "KAFKA_TOPIC" else "bpmn.worker::"
                )
            ]
            assert len(refs) == 1
            assert not await conn.fetchval(
                "SELECT count(*) FROM search_discovery_entries WHERE snapshot_id=$1 AND kind=$2",
                source_id,
                kind,
            )
            matches = await search.search_discovery_entries(
                conn, kind, key, allowed_repository_keys=list(grants)
            )
            assert len(matches["items"]) == 2 and matches["resolution"] == "AMBIGUOUS"
            assert matches["coverage"]["status"] == "PARTIAL"
            if kind == "BPMN_WORKER":
                workers = [
                    f
                    for f in facts
                    if isinstance(f, Symbol) and f.symbol_kind == "BPMN_WORKER"
                ]
                links = [
                    f
                    for f in facts
                    if isinstance(f, Relation)
                    and f.relation_kind == RelationKind.BPMN_WORKER_HANDLER
                ]
                assert len(workers) == len(links) == 1
                assert {e.rule for e in links[0].evidence} == {
                    "job.worker",
                    "job.method",
                }
                assert matches["items"][0]["qualifier"]["engine"] == "camunda8"
            context = await select_context(
                conn,
                "LATEST_INDEXED",
                ("source", "target"),
                allowed_repositories=grants,
            )

            async def resolve(ctx=context, allowed=grants, limit=50):
                return await search.resolve_external_reference(
                    conn,
                    "source",
                    refs[0].id,
                    ctx,
                    allowed_repositories=allowed,
                    limit=limit,
                )

            result = await resolve()
            assert (
                result.status == "PARTIAL"
                and result.target is None
                and len(result.candidates) == 1
            )
            assert result.candidates[0].evidence.available
            await resolver_cache.warm_resolver_cache(
                conn, "source", refs[0].id, context, allowed_repositories=grants
            )
            assert await resolve() == result
            with pytest.raises(PermissionError):
                await resolve(allowed=frozenset(("source",)))
            multi = await select_context(
                conn, "LATEST_INDEXED", tuple(repos), allowed_repositories=grants
            )
            assert (await resolve(multi)).status == "AMBIGUOUS"
            bounded = await resolve(multi, limit=1)
            assert bounded.status == "PARTIAL" and bounded.truncated
            pins = tuple(
                SnapshotPin(repository_key=s.repository_key, snapshot_id=s.snapshot_id)
                for s in context.selections
            )
            pinned = await select_context(
                conn,
                "PINNED_SNAPSHOTS",
                ("source", "target"),
                pins=pins,
                allowed_repositories=grants,
            )
            renamed, _ = await stage(
                conn, repos["target"], kind, declaration.replace(key, "renamed")
            )
            await publish(conn, repos["target"], renamed, target_id)
            latest = await select_context(
                conn,
                "LATEST_INDEXED",
                ("source", "target"),
                allowed_repositories=grants,
            )
            assert (await resolve(latest)).status == "UNRESOLVED"
            assert (await resolve(pinned)).candidates[0].snapshot_id == target_id
            assert await discovery.refresh_discovery(conn, "target") == next(
                s.generation for s in latest.selections if s.repository_key == "target"
            )
            await rollback_publication(
                conn, repos["target"], target_id, expected_snapshot_id=renamed
            )
            assert len((await resolve()).candidates) == 1
            assert not await conn.fetchval(
                "SELECT count(*) FROM ucm_relations r JOIN ucm_entities e ON e.snapshot_id=r.snapshot_id AND e.entity_id=r.target_id WHERE r.snapshot_id=$1 AND e.repository_id<>$2",
                source_id,
                repos["source"],
            )
        finally:
            await conn.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["KAFKA_TOPIC", "BPMN_WORKER"])
def test_dynamic_disabled_and_reference_only_do_not_define_resources(
    database_url, kind
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            repo = await repository(conn, "target")
            java = (
                KAFKA_SEND
                + "\nimport org.apache.kafka.clients.admin.NewTopic; class Topics { Object topic(String key) { return new NewTopic(key,1,(short)1); } }"
                if kind == "KAFKA_TOPIC"
                else WORKER.replace('type="accounting"', 'type="${worker}"')
                + '\nclass Disabled { @io.camunda.spring.client.annotation.JobWorker(type="accounting",enabled=false) void handle() {} }'
            )
            # Keep Java imports before declarations, so the negative isn't merely a parse failure.
            if kind == "KAFKA_TOPIC":
                java = java.replace(
                    "\nimport org.apache.kafka.clients.admin.NewTopic;", ""
                )
                java = "import org.apache.kafka.clients.admin.NewTopic;\n" + java
            sid, _ = await stage(
                conn, repo, kind, java, xml=TASK if kind == "BPMN_WORKER" else None
            )
            await publish(conn, repo, sid)
            assert not await conn.fetchval(
                "SELECT count(*) FROM search_discovery_entries WHERE snapshot_id=$1 AND kind=$2",
                sid,
                kind,
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_kafka_explicit_cluster_environment_filters_and_refresh_rollback(
    database_url, monkeypatch
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            repos = {
                key: await repository(conn, key)
                for key in ("source", "target", "other")
            }
            versions = {}
            facts = None
            for key, java, cluster in (
                ("source", KAFKA_SEND, "a:9092"),
                ("target", KAFKA_DECLARE, "a:9092"),
                ("other", KAFKA_DECLARE, "b:9092"),
            ):
                sid, current = await stage(
                    conn,
                    repos[key],
                    "KAFKA_TOPIC",
                    java,
                    config=f"spring.kafka.bootstrap-servers={cluster}\nspring.profiles.active=prod\n",
                )
                versions[key] = sid
                await publish(conn, repos[key], sid)
                if key == "source":
                    facts = current
            grants = frozenset(repos)
            ctx = await select_context(
                conn, "LATEST_INDEXED", tuple(repos), allowed_repositories=grants
            )
            ref = next(
                f
                for f in facts
                if isinstance(f, ExternalReference)
                and f.selector.qualified_name.startswith("kafka.topic::")
            )
            result = await search.resolve_external_reference(
                conn, "source", ref.id, ctx, allowed_repositories=grants
            )
            assert result.status == "PARTIAL" and [
                c.repository_key for c in result.candidates
            ] == ["target"]
            exact = await search.search_discovery_entries(
                conn,
                "KAFKA_TOPIC",
                "payments",
                allowed_repository_keys=list(repos),
                qualifier={"cluster": "b:9092", "environment": "prod"},
            )
            assert [x["repository_key"] for x in exact["items"]] == ["other"]
            previous = await conn.fetchval(
                "SELECT generation FROM search_discovery_generations WHERE snapshot_id=$1",
                versions["target"],
            )

            class Interrupted:
                def __getattr__(self, key):
                    return getattr(conn, key)

                async def execute(self, sql, *args):
                    if "WITH symbols AS" in sql:
                        raise asyncio.CancelledError()
                    return await conn.execute(sql, *args)

            with monkeypatch.context() as patch:
                patch.setattr(discovery, "VERSION", "discovery/test-interrupted")
                with pytest.raises(asyncio.CancelledError):
                    await discovery.refresh_discovery(Interrupted(), "target")
            assert (
                await conn.fetchval(
                    "SELECT generation FROM search_discovery_generations WHERE snapshot_id=$1",
                    versions["target"],
                )
                == previous
            )
            assert (
                await search.resolve_external_reference(
                    conn, "source", ref.id, ctx, allowed_repositories=grants
                )
            ) == result
        finally:
            await conn.close()

    asyncio.run(run())


def test_camunda7_handler_contract_and_engine_are_required(database_url):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            await migrate(conn)
            repo = await repository(conn, "target")
            java = """import org.camunda.bpm.client.spring.annotation.ExternalTaskSubscription;
import org.camunda.bpm.client.task.ExternalTaskHandler;
import org.camunda.bpm.client.task.ExternalTask;
import org.camunda.bpm.client.task.ExternalTaskService;
@ExternalTaskSubscription("accounting") class Worker implements ExternalTaskHandler {
 public void execute(ExternalTask task, ExternalTaskService service) {} }
@ExternalTaskSubscription("accounting") class Pretender { public void execute() {} }"""
            sid, _ = await stage(conn, repo, "BPMN_WORKER", java)
            await publish(conn, repo, sid)
            result = await search.search_discovery_entries(
                conn,
                "BPMN_WORKER",
                "accounting",
                allowed_repository_keys=["target"],
                qualifier={"engine": "camunda7"},
            )
            assert len(result["items"]) == 1
            assert result["items"][0]["qualifier"]["handler_id"]
            wrong = await search.search_discovery_entries(
                conn,
                "BPMN_WORKER",
                "accounting",
                allowed_repository_keys=["target"],
                qualifier={"engine": "camunda8"},
            )
            assert not wrong["items"]
        finally:
            await conn.close()

    asyncio.run(run())
