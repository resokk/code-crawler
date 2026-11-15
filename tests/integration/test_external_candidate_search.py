import asyncio

import asyncpg
import pytest
from test_publication import create, setup

from code_crawler import search, snapshots
from code_crawler.external_candidates import CandidateResolution
from code_crawler.ingestion import UcmBatch
from code_crawler.publication import (
    publish_snapshot,
    rollback_publication,
    validate_snapshot,
)
from code_crawler.resolver_context import select_context
from code_crawler.source_evidence import read_source_fragment
from code_crawler.ucm import (
    CallableSignature,
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    HttpSelector,
    Symbol,
    SymbolSelector,
    TypeRef,
    callable_key,
    logical_id,
)

pytestmark = pytest.mark.integration
FQN = "remote.Client.m"


def source_batch(factory, repo):
    batch = factory(repo)
    method = next(e for e in batch.entities if isinstance(e, Symbol) and e.name == "m")
    proofs = (
        Evidence(
            source_range=method.source_range,
            analyzer="fixture",
            analyzer_version="1",
            rule="external.signature",
            description="Explicit external declaration selector",
        ),
    )
    refs = []
    for name, selector, certainty, hint in (
        (
            "exact",
            SymbolSelector(qualified_name=FQN, parameter_type_names=("A", "String")),
            Certainty.STATIC_PROVEN,
            None,
        ),
        ("name", SymbolSelector(qualified_name=FQN), Certainty.STATIC_PROVEN, None),
        (
            "partial",
            SymbolSelector(qualified_name=FQN, parameter_type_names=("A", "String")),
            Certainty.INFERRED,
            None,
        ),
        (
            "missing",
            SymbolSelector(qualified_name="missing.Client.m", parameter_type_names=()),
            Certainty.STATIC_PROVEN,
            None,
        ),
        (
            "kafka",
            SymbolSelector(qualified_name="kafka.topic::orders"),
            Certainty.STATIC_PROVEN,
            None,
        ),
        (
            "http",
            HttpSelector(method="GET", path="/x", service="service"),
            Certainty.STATIC_PROVEN,
            None,
        ),
        (
            "version",
            SymbolSelector(qualified_name=FQN, parameter_type_names=("A", "String")),
            Certainty.STATIC_PROVEN,
            "unknown-version",
        ),
    ):
        key = "external:" + name
        refs.append(
            ExternalReference(
                repository_id=str(repo),
                logical_key=key,
                id=logical_id(str(repo), EntityType.EXTERNAL_REFERENCE, key),
                name=name,
                source=EntityRef(entity_type=method.entity_type, id=method.id),
                selector=selector,
                version_hint=hint,
                reason="external target deferred",
                evidence=proofs,
                certainty=certainty,
                coverage=Coverage(
                    capability="fixture.external",
                    analyzer_version="1",
                    status="COMPLETE",
                ),
            )
        )
    return UcmBatch(repository_id=repo, entities=(*batch.entities, *refs)), {
        e.name: e.id for e in refs
    }


def target_batch(factory, repo, count=0, fqn=FQN, evidence=True):
    batch = factory(repo)
    entities = []
    template = None
    for e in batch.entities:
        if isinstance(e, Symbol) and e.name == "m":
            template = e.model_copy(
                update={
                    "qualified_name": fqn,
                    "source_range": e.source_range if evidence else None,
                }
            )
            entities.append(template)
        else:
            entities.append(e)
    for n in range(count):
        owner = f"fanout:{n}"
        key = callable_key(owner, template.name, template.signature)
        entities.append(
            Symbol(
                repository_id=str(repo),
                logical_key=key,
                id=logical_id(str(repo), EntityType.SYMBOL, key),
                name=template.name,
                symbol_kind="METHOD",
                qualified_name=fqn,
                owner_key=owner,
                signature=template.signature,
                source_range=template.source_range,
            )
        )
    return UcmBatch(repository_id=repo, entities=tuple(entities))


def test_external_candidates_unique_ambiguous_missing_partial_versions_and_fanout(
    database_url, ucm_batch_factory
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            source = await setup(conn)
            repos = {"repo": source}
            for key in ("target", "other", "large", "opaque"):
                repos[key] = await snapshots.register_repository(
                    conn,
                    snapshots.RepositoryInput(
                        repository_key=key, display_name=key, source="fixture"
                    ),
                )
            batch, refs = source_batch(ucm_batch_factory, source)
            source_snapshot = await create(conn, source, batch)
            await validate_snapshot(conn, source_snapshot)
            await publish_snapshot(
                conn, source, source_snapshot, expected_snapshot_id=None
            )
            original = await conn.fetchval(
                "SELECT row_to_json(e)::text FROM ucm_external_references e WHERE snapshot_id=$1 AND entity_id=$2",
                source_snapshot,
                refs["exact"],
            )
            versions = {}
            for key, count in (
                ("target", 0),
                ("other", 0),
                ("large", 1000),
                ("opaque", 0),
            ):
                snap = await create(
                    conn,
                    repos[key],
                    target_batch(
                        ucm_batch_factory, repos[key], count, evidence=key != "opaque"
                    ),
                )
                await validate_snapshot(conn, snap)
                await publish_snapshot(
                    conn, repos[key], snap, expected_snapshot_id=None
                )
                versions[key] = snap
            grants = frozenset(repos)

            async def context(*keys):
                return await select_context(
                    conn, "LATEST_INDEXED", ("repo", *keys), allowed_repositories=grants
                )

            single = await context("target")

            async def resolve(name, ctx=single, **kwargs):
                return await search.resolve_external_reference(
                    conn, "repo", refs[name], ctx, allowed_repositories=grants, **kwargs
                )

            result = await resolve("exact")
            assert (
                result.status == "RESOLVED" and result.target.repository_key == "target"
            )
            assert result.target.snapshot_id == versions["target"]
            assert result.context_fingerprint == single.fingerprint
            assert (
                CandidateResolution.model_validate_json(result.model_dump_json())
                == result
            )
            evidence = result.target.evidence
            fragment = await read_source_fragment(
                conn,
                evidence.repository_id,
                evidence.snapshot_id,
                evidence.source_range,
            )
            assert (
                fragment.provenance.path == evidence.path
                and fragment.provenance.content_sha256 == evidence.content_sha256
            )
            assert (await resolve("name")).status == "PARTIAL"
            partial = await resolve("partial")
            opaque = await resolve("exact", await context("opaque"))
            assert (
                opaque.status == "PARTIAL"
                and not opaque.candidates[0].evidence.available
            )
            assert (
                partial.status == "PARTIAL"
                and partial.candidates[0].certainty == Certainty.INFERRED
            )
            assert (await resolve("missing")).status == "UNRESOLVED"
            assert (await resolve("version")).status == "UNRESOLVED"
            unsupported = await resolve("kafka")
            assert (
                unsupported.status == "UNRESOLVED"
                and unsupported.coverage.status == "UNSUPPORTED"
            )
            assert (await resolve("http")).status == "UNRESOLVED"
            ambiguous = await resolve("exact", await context("target", "other"))
            assert (
                ambiguous.status == "AMBIGUOUS"
                and len(ambiguous.candidates) == 2
                and ambiguous.target is None
            )
            fanout = await resolve("exact", await context("large"), limit=3)
            assert (
                fanout.status == "PARTIAL"
                and fanout.truncated
                and len(fanout.candidates) == 3
            )
            truncated_one = await resolve("exact", await context("large"), limit=1)
            assert truncated_one.status == "PARTIAL" and truncated_one.target is None
            with pytest.raises(PermissionError):
                await search.resolve_external_reference(
                    conn,
                    "repo",
                    refs["exact"],
                    single,
                    allowed_repositories=frozenset(("repo",)),
                )
            with pytest.raises(ValueError, match="entity does not exist"):
                await search.resolve_external_reference(
                    conn, "target", refs["exact"], single, allowed_repositories=grants
                )
            from uuid import uuid4

            stale = single.model_copy(
                update={
                    "selections": tuple(
                        s.model_copy(update={"generation": uuid4()})
                        if s.repository_key == "target"
                        else s
                        for s in single.selections
                    )
                }
            )
            unavailable = await resolve("exact", stale)
            assert (
                unavailable.status == "PARTIAL"
                and unavailable.unavailable_repositories == ("target",)
            )
            assert not unavailable.candidates
            changed = await create(
                conn,
                repos["target"],
                target_batch(ucm_batch_factory, repos["target"], fqn="new.Client.m"),
            )
            await validate_snapshot(conn, changed)
            await publish_snapshot(
                conn, repos["target"], changed, expected_snapshot_id=versions["target"]
            )
            assert (
                await resolve("exact", await context("target"))
            ).status == "UNRESOLVED"
            assert (await resolve("exact", single)).status == "RESOLVED"
            await rollback_publication(
                conn, repos["target"], versions["target"], expected_snapshot_id=changed
            )
            assert (
                await resolve("exact", await context("target"))
            ).status == "RESOLVED"
            assert original == await conn.fetchval(
                "SELECT row_to_json(e)::text FROM ucm_external_references e WHERE snapshot_id=$1 AND entity_id=$2",
                source_snapshot,
                refs["exact"],
            )
            assert (
                await conn.fetchval(
                    "SELECT resolution FROM ucm_external_references WHERE snapshot_id=$1 AND entity_id=$2",
                    source_snapshot,
                    refs["exact"],
                )
                == "UNRESOLVED"
            )
        finally:
            await conn.close()

    asyncio.run(run())


def test_database_alias_resolves_full_identity_without_cross_database_name_match(
    database_url, ucm_batch_factory
):
    import json

    from test_database_identity_storage import document

    from code_crawler.database_schema import import_schema, schema_objects
    from code_crawler.ucm import (
        DatabaseContext,
        DatabaseObject,
        DatabaseSelector,
        SourceFile,
    )

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            source = await setup(conn)
            catalog_docs = {key: document(key) for key in ("prod", "other")}
            for doc in catalog_docs.values():
                await import_schema(conn, doc)
            batch, refs = source_batch(ucm_batch_factory, source)
            file = next(e for e in batch.entities if isinstance(e, SourceFile))
            template = next(
                e
                for e in batch.entities
                if isinstance(e, ExternalReference) and e.id == refs["exact"]
            )
            doc = catalog_docs["prod"]
            context_key = json.dumps(
                ["database.context", file.id, "primary", "prod", "v1", ["public"]],
                separators=(",", ":"),
            )
            db_context = DatabaseContext(
                repository_id=str(source),
                logical_key=context_key,
                id=logical_id(str(source), EntityType.DATABASE_CONTEXT, context_key),
                name="primary",
                projection_file_id=file.id,
                connection_key="primary",
                database_key="prod",
                version_key="v1",
                schema_fingerprint=doc.fingerprint,
                search_path=("public",),
                source_range=template.evidence[0].source_range,
            )
            db_ref = template.model_copy(
                update={
                    "selector": DatabaseSelector(connection="primary", table="users")
                }
            )
            entities = tuple(db_ref if e.id == db_ref.id else e for e in batch.entities)
            source_snapshot = await create(
                conn,
                source,
                UcmBatch(repository_id=source, entities=(*entities, db_context)),
            )
            await validate_snapshot(conn, source_snapshot)
            await publish_snapshot(
                conn, source, source_snapshot, expected_snapshot_id=None
            )
            repositories = {"repo": source}
            targets = {}
            for key, doc in catalog_docs.items():
                repo = await snapshots.register_repository(
                    conn,
                    snapshots.RepositoryInput(
                        repository_key=key, display_name=key, source="fixture"
                    ),
                )
                repositories[key] = repo
                base = ucm_batch_factory(repo)
                target_file = next(
                    e for e in base.entities if isinstance(e, SourceFile)
                )
                table = next(o for o in schema_objects(doc) if o.object_kind == "TABLE")
                logical_key = json.dumps(
                    ["database.object", target_file.id, table.object_key],
                    separators=(",", ":"),
                )
                obj = DatabaseObject(
                    repository_id=str(repo),
                    logical_key=logical_key,
                    id=logical_id(str(repo), EntityType.DATABASE_OBJECT, logical_key),
                    name="users",
                    projection_file_id=target_file.id,
                    database_key=key,
                    version_key="v1",
                    schema_fingerprint=doc.fingerprint,
                    object_key=table.object_key,
                    object_kind="TABLE",
                    catalog_name=doc.catalog_name,
                    schema_name="public",
                    table_name="users",
                    source_range=db_ref.evidence[0].source_range.model_copy(
                        update={"source_file_id": target_file.id}
                    ),
                )
                targets[key] = obj
                snap = await create(
                    conn,
                    repo,
                    UcmBatch(repository_id=repo, entities=(*base.entities, obj)),
                )
                await validate_snapshot(conn, snap)
                await publish_snapshot(conn, repo, snap, expected_snapshot_id=None)
            grants = frozenset(repositories)
            selected = await select_context(
                conn, "LATEST_INDEXED", tuple(repositories), allowed_repositories=grants
            )
            resolved = await search.resolve_external_reference(
                conn, "repo", db_ref.id, selected, allowed_repositories=grants
            )
            assert (
                resolved.status == "RESOLVED"
                and resolved.target.target.id == targets["prod"].id
            )
            assert (
                len(resolved.candidates) == 1
                and resolved.target.repository_key == "prod"
            )
            # The same alias in another file is not the origin's connection binding.
            other_file = file.model_copy(
                update={
                    "logical_key": "B.java",
                    "path": "B.java",
                    "name": "B.java",
                    "id": logical_id(str(source), EntityType.SOURCE_FILE, "B.java"),
                }
            )
            other_key = json.dumps(
                [
                    "database.context",
                    other_file.id,
                    "primary",
                    "prod",
                    "v1",
                    ["public"],
                ],
                separators=(",", ":"),
            )
            unrelated = db_context.model_copy(
                update={
                    "logical_key": other_key,
                    "id": logical_id(
                        str(source), EntityType.DATABASE_CONTEXT, other_key
                    ),
                    "projection_file_id": other_file.id,
                    "source_range": db_context.source_range.model_copy(
                        update={"source_file_id": other_file.id}
                    ),
                }
            )
            changed_batch = UcmBatch(
                repository_id=source, entities=(*entities, unrelated, other_file)
            )
            new_source = await create(conn, source, changed_batch)
            await validate_snapshot(conn, new_source)
            await publish_snapshot(
                conn, source, new_source, expected_snapshot_id=source_snapshot
            )
            current = await select_context(
                conn, "LATEST_INDEXED", tuple(repositories), allowed_repositories=grants
            )
            result = await search.resolve_external_reference(
                conn, "repo", db_ref.id, current, allowed_repositories=grants
            )
            assert result.status == "UNRESOLVED" and not result.candidates
            old_result = await search.resolve_external_reference(
                conn, "repo", db_ref.id, selected, allowed_repositories=grants
            )
            assert old_result.status == "RESOLVED"
        finally:
            await conn.close()

    asyncio.run(run())


def test_http_contract_candidates_require_explicit_service_context_and_stay_partial(
    database_url, ucm_batch_factory, tmp_path
):
    from code_crawler import repos
    from code_crawler.openapi_adapter import OpenApiSourceAdapter
    from code_crawler.resolver_context import DeploymentBinding, register_deployment
    from code_crawler.source_adapters import AdapterRegistry, index_sources

    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            source = await setup(conn)
            batch, refs = source_batch(ucm_batch_factory, source)
            source_snapshot = await create(conn, source, batch)
            await validate_snapshot(conn, source_snapshot)
            await publish_snapshot(
                conn, source, source_snapshot, expected_snapshot_id=None
            )
            await repos.git("init", cwd=tmp_path)
            await repos.git("config", "user.name", "HTTP Test", cwd=tmp_path)
            await repos.git(
                "config", "user.email", "test@example.invalid", cwd=tmp_path
            )
            (tmp_path / "api.yaml").write_text(
                'openapi: 3.1.0\ninfo: {title: API, version: v1}\npaths:\n  /x:\n    get:\n      responses: {"200": {description: OK}}\n'
            )
            await repos.git("add", ".", cwd=tmp_path)
            await repos.git("commit", "-m", "fixture", cwd=tmp_path)
            api = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="api", display_name="api", source=str(tmp_path)
                ),
            )
            indexed = await index_sources(
                conn, api, tmp_path, AdapterRegistry((OpenApiSourceAdapter(),))
            )
            await validate_snapshot(conn, indexed.snapshot_id)
            await publish_snapshot(
                conn, api, indexed.snapshot_id, expected_snapshot_id=None
            )
            grants = frozenset(("repo", "api"))
            latest = await select_context(
                conn, "LATEST_INDEXED", ("repo", "api"), allowed_repositories=grants
            )
            missing_binding = await search.resolve_external_reference(
                conn, "repo", refs["http"], latest, allowed_repositories=grants
            )
            assert (
                missing_binding.status == "UNRESOLVED"
                and not missing_binding.candidates
            )
            await register_deployment(
                conn,
                "service-deploy",
                (
                    DeploymentBinding(
                        repository_key="repo",
                        snapshot_id=source_snapshot,
                        service_key="caller",
                    ),
                    DeploymentBinding(
                        repository_key="api",
                        snapshot_id=indexed.snapshot_id,
                        service_key="service",
                    ),
                ),
                allowed_repositories=grants,
            )
            deployed = await select_context(
                conn,
                "DEPLOYMENT_CONTEXT",
                ("repo", "api"),
                deployment_key="service-deploy",
                allowed_repositories=grants,
            )
            result = await search.resolve_external_reference(
                conn, "repo", refs["http"], deployed, allowed_repositories=grants
            )
            assert (
                result.status == "PARTIAL"
                and result.target is None
                and len(result.candidates) == 1
            )
            candidate = result.candidates[0]
            assert (
                candidate.repository_key == "api"
                and candidate.snapshot_id == indexed.snapshot_id
            )
            assert (
                candidate.evidence.path == "api.yaml" and candidate.evidence.available
            )
            assert candidate.certainty == Certainty.INFERRED
            assert candidate.rule == "selector.exact.http"
            assert candidate.contract_id is not None
            await register_deployment(
                conn,
                "wrong-service",
                (
                    DeploymentBinding(
                        repository_key="repo",
                        snapshot_id=source_snapshot,
                        service_key="caller",
                    ),
                    DeploymentBinding(
                        repository_key="api",
                        snapshot_id=indexed.snapshot_id,
                        service_key="unrelated-service",
                    ),
                ),
                allowed_repositories=grants,
            )
            wrong = await select_context(
                conn,
                "DEPLOYMENT_CONTEXT",
                ("repo", "api"),
                deployment_key="wrong-service",
                allowed_repositories=grants,
            )
            assert not (
                await search.resolve_external_reference(
                    conn, "repo", refs["http"], wrong, allowed_repositories=grants
                )
            ).candidates
        finally:
            await conn.close()

    asyncio.run(run())


def test_matching_adapter_placeholders_remain_partial_with_complete_source_facts(
    database_url, ucm_batch_factory
):
    async def run():
        conn = await asyncpg.connect(database_url)
        try:
            source = await setup(conn)
            target = await snapshots.register_repository(
                conn,
                snapshots.RepositoryInput(
                    repository_key="target", display_name="target", source="fixture"
                ),
            )
            source_facts, _ = source_batch(ucm_batch_factory, source)
            template = next(
                e
                for e in source_facts.entities
                if isinstance(e, ExternalReference) and e.name == "exact"
            )
            target_facts = target_batch(ucm_batch_factory, target)
            target_method = next(
                e
                for e in target_facts.entities
                if isinstance(e, Symbol) and e.name == "m"
            )
            refs, methods = [], []
            for index, marker in enumerate(
                (
                    "kotlin.unknown",
                    "groovy.dynamic",
                    "vbscript.Variant",
                    "List<unknown>",
                    "Map<String,groovy.dynamic>",
                    "any",
                )
            ):
                name = f"uncertain{index}"
                fqn = "remote.Client." + name
                key = f"external:placeholder:{index}"
                refs.append(
                    template.model_copy(
                        update={
                            "logical_key": key,
                            "id": logical_id(
                                str(source), EntityType.EXTERNAL_REFERENCE, key
                            ),
                            "name": name,
                            "selector": SymbolSelector(
                                qualified_name=fqn, parameter_type_names=(marker,)
                            ),
                        }
                    )
                )
                signature = CallableSignature(parameter_types=(TypeRef(name=marker),))
                method_key = callable_key(target_method.owner_key, name, signature)
                methods.append(
                    Symbol(
                        repository_id=str(target),
                        logical_key=method_key,
                        id=logical_id(str(target), EntityType.SYMBOL, method_key),
                        name=name,
                        symbol_kind="METHOD",
                        qualified_name=fqn,
                        owner_key=target_method.owner_key,
                        signature=signature,
                        source_range=target_method.source_range,
                    )
                )
            source_snapshot = await create(
                conn,
                source,
                UcmBatch(
                    repository_id=source, entities=(*source_facts.entities, *refs)
                ),
            )
            target_snapshot = await create(
                conn,
                target,
                UcmBatch(
                    repository_id=target, entities=(*target_facts.entities, *methods)
                ),
            )
            for repo, sid in ((source, source_snapshot), (target, target_snapshot)):
                await validate_snapshot(conn, sid)
                await publish_snapshot(conn, repo, sid, expected_snapshot_id=None)
            grants = frozenset({"repo", "target"})
            context = await select_context(
                conn, "LATEST_INDEXED", ("repo", "target"), allowed_repositories=grants
            )
            before = await conn.fetchval("SELECT count(*) FROM ucm_relations")
            for reference in refs:
                result = await search.resolve_external_reference(
                    conn, "repo", reference.id, context, allowed_repositories=grants
                )
                assert result.reference_certainty == Certainty.STATIC_PROVEN
                assert result.reference_coverage.status == "COMPLETE"
                assert result.status == "PARTIAL" and result.target is None
                assert len(result.candidates) == 1
                assert result.candidates[0].certainty == Certainty.INFERRED
                assert result.coverage.analyzer_version == "2"
                assert "unknown parameter type identity" in result.reasons
            assert await conn.fetchval("SELECT count(*) FROM ucm_relations") == before
        finally:
            await conn.close()

    asyncio.run(run())
