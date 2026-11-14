import asyncio
import hashlib
from uuid import UUID

import pytest

from code_crawler.bpmn_adapter import BPMN, CAMUNDA, ZEEBE, BpmnSourceAdapter
from code_crawler.bpmn_bindings import FLOWABLE
from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.ucm import (
    Certainty,
    EntityType,
    ExternalReference,
    Relation,
    RelationKind,
    SourceAnalysis,
    SourceFile,
    SqlExecute,
    Symbol,
    Value,
    logical_id,
)

REPO = "00000000-0000-0000-0000-000000000002"
IMPORTS = """package app;
import org.camunda.bpm.engine.delegate.JavaDelegate;
import org.camunda.bpm.engine.delegate.DelegateExecution;
import org.springframework.stereotype.Component;
"""
DELEGATE = (
    IMPORTS
    + """@Component("charge") class Charge implements JavaDelegate {
 public void execute(DelegateExecution e) {
    Object amount=e.getVariable("amount"); e.setVariable("result", amount);
 }
}"""
)


def bpmn(body: str) -> str:
    return f'''<definitions xmlns="{BPMN}" xmlns:c="{CAMUNDA}" xmlns:z="{ZEEBE}" xmlns:f="{FLOWABLE}">
    <process id="process">{body}</process></definitions>'''


def captured(path: str, text: str, repo: str = REPO) -> SourceInput:
    content = text.encode()
    return SourceInput(
        SourceFile(
            repository_id=repo,
            logical_key=path,
            name=path,
            path=path,
            language="java" if path.endswith(".java") else "bpmn",
            id=logical_id(repo, EntityType.SOURCE_FILE, path),
            content_sha256=hashlib.sha256(content).hexdigest(),
        ),
        content,
    )


def analyze(
    files: dict[str, str],
    java_profile: str = "calls",
    bpmn_profile: str = "auto",
    repo: str = REPO,
):
    sources = tuple(captured(path, text, repo) for path, text in sorted(files.items()))

    async def run():
        prepared = await AdapterRegistry(
            (BpmnSourceAdapter(bpmn_profile), JavaSourceAdapter(profile=java_profile))
        ).prepare(sources)
        analyses = await prepared(sources)
        batch = UcmBatch(
            repository_id=UUID(repo),
            entities=(
                *(s.file for s in sources),
                *(e for a in analyses for e in a.entities),
            ),
        )
        assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
        return batch, prepared, analyses

    return asyncio.run(run())


def relations(batch: UcmBatch, kind: RelationKind) -> list[Relation]:
    return [
        e for e in batch.entities if isinstance(e, Relation) and e.relation_kind == kind
    ]


def binding(batch: UcmBatch) -> Relation:
    found = relations(batch, RelationKind.BPMN_HANDLER)
    assert len(found) == 1
    return found[0]


def test_spring_bean_resolves_to_canonical_method_with_both_evidence() -> None:
    batch, _, analyses = analyze(
        {
            "Charge.java": DELEGATE,
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
        },
        java_profile="orm",
    )
    link = binding(batch)
    target = next(e for e in batch.entities if e.id == link.resolution.target.id)
    assert isinstance(target, Symbol) and target.symbol_kind == "METHOD"
    assert target.qualified_name == "app.Charge.execute"
    assert link.resolution.status == "RESOLVED" and link.certainty == Certainty.INFERRED
    paths = {e.id: e.path for e in batch.entities if isinstance(e, SourceFile)}
    assert {paths[e.source_range.source_file_id] for e in link.evidence} == {
        "Charge.java",
        "p.bpmn",
    }
    assert next(a for a in analyses if a.path == "p.bpmn").dependencies == (
        "Charge.java",
    )
    assert not any(
        isinstance(e, ExternalReference)
        and e.selector.qualified_name.startswith("bpmn.delegateExpression")
        for e in batch.entities
    )


def test_duplicate_compatible_beans_stay_ambiguous() -> None:
    batch, _, _ = analyze(
        {
            "A.java": DELEGATE,
            "B.java": DELEGATE.replace("Charge", "Other"),
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
        }
    )
    link = binding(batch)
    assert (
        link.resolution.status == "AMBIGUOUS" and len(link.resolution.candidates) == 2
    )
    assert link.certainty == Certainty.INFERRED and link.resolution.target is None


@pytest.mark.parametrize(
    "engine,profile,namespace",
    [
        ("org.camunda.bpm", "camunda7", "c"),
        ("org.flowable", "flowable6", "f"),
        ("org.flowable", "flowable7", "f"),
    ],
)
def test_profile_specific_java_delegate_contracts(
    engine: str, profile: str, namespace: str
) -> None:
    java = DELEGATE.replace("org.camunda.bpm", engine)
    batch, _, _ = analyze(
        {
            "Charge.java": java,
            "p.bpmn": bpmn(f'<serviceTask id="t" {namespace}:class="app.Charge"/>'),
        },
        bpmn_profile=profile,
    )
    assert binding(batch).resolution.status == "RESOLVED"
    wrong = "f" if namespace == "c" else "c"
    other, _, _ = analyze(
        {
            "Charge.java": java,
            "p.bpmn": bpmn(f'<serviceTask id="t" {wrong}:class="app.Charge"/>'),
        }
    )
    assert binding(other).resolution.status == "UNRESOLVED"


@pytest.mark.parametrize(
    "java",
    [
        IMPORTS
        + '@Component("charge") class Charge { public void execute(DelegateExecution e) {} }',
        'package app; @Component("charge") class Charge implements org.camunda.bpm.engine.delegate.JavaDelegate { public void execute(org.camunda.bpm.engine.delegate.DelegateExecution e) {} }',
        DELEGATE.replace(
            "public void execute(DelegateExecution e)", "public void execute(Object e)"
        ).replace(
            'Object amount=e.getVariable("amount"); e.setVariable("result", amount);',
            "",
        ),
        DELEGATE.replace("public void execute", "public static void execute"),
    ],
)
def test_namesakes_incompatible_types_and_unresolved_annotations_do_not_bind(
    java: str,
) -> None:
    batch, _, _ = analyze(
        {
            "Charge.java": java,
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
        }
    )
    assert binding(batch).resolution.status == "UNRESOLVED"
    assert any(
        isinstance(e, ExternalReference)
        and e.selector.qualified_name == "bpmn.delegateExpression::${charge}"
        for e in batch.entities
    )


@pytest.mark.parametrize(
    "expression",
    [
        "${charge.choose(execution)}",
        "${charge.value}",
        "${unknown}",
        "#{charge[which]}",
    ],
)
def test_dynamic_or_missing_bean_is_deferred(expression: str) -> None:
    batch, _, _ = analyze(
        {
            "Charge.java": DELEGATE,
            "p.bpmn": bpmn(
                f'<serviceTask id="t" c:delegateExpression="{expression}"/>'
            ),
        }
    )
    assert binding(batch).resolution.status == "UNRESOLVED"
    assert not relations(batch, RelationKind.EXECUTES_SQL)
    assert any(
        isinstance(e, ExternalReference) and e.certainty == Certainty.UNKNOWN
        for e in batch.entities
    )


@pytest.mark.parametrize(
    "annotation,expected",
    [
        ("Component", "charge"),
        ("Service", "charge"),
        ("Component", "URLWorker"),
        ("Component", "u2"),
    ],
)
def test_default_spring_names_and_acronyms(annotation: str, expected: str) -> None:
    name = {"charge": "Charge", "URLWorker": "URLWorker", "u2": "U2"}[expected]
    java = (
        DELEGATE.replace(
            "import org.springframework.stereotype.Component;",
            f"import org.springframework.stereotype.{annotation};",
        )
        .replace('@Component("charge")', "@" + annotation)
        .replace("class Charge", "class " + name)
    )
    batch, _, _ = analyze(
        {
            "Worker.java": java,
            "p.bpmn": bpmn(
                f'<serviceTask id="t" c:delegateExpression="${{{expected}}}"/>'
            ),
        }
    )
    assert binding(batch).resolution.status == "RESOLVED"


def test_bean_factory_aliases_and_interface_return_type_preserve_ambiguity() -> None:
    config = (
        IMPORTS
        + """import org.springframework.context.annotation.Bean;
    class Config { @Bean(name={"charge", "alias"}) JavaDelegate delegate() {return new Charge();} }"""
    )
    base = DELEGATE.replace('@Component("charge")', "")
    batch, _, _ = analyze(
        {
            "Charge.java": base,
            "Config.java": config,
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${alias}"/>'),
        }
    )
    assert binding(batch).resolution.status == "RESOLVED"
    ambiguous, _, _ = analyze(
        {
            "Charge.java": base,
            "Other.java": base.replace("Charge", "Other"),
            "Config.java": config,
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
        }
    )
    assert binding(ambiguous).resolution.status == "AMBIGUOUS"


def test_duplicate_registration_of_one_handler_remains_partial() -> None:
    config = (
        IMPORTS
        + """import org.springframework.context.annotation.Bean;
    class Config { @Bean("charge") Charge duplicate() {return new Charge();} }"""
    )
    batch, _, _ = analyze(
        {
            "Charge.java": DELEGATE,
            "Config.java": config,
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
        }
    )
    assert binding(batch).resolution.status == "PARTIAL"
    assert len(binding(batch).resolution.candidates) == 1


@pytest.mark.parametrize(
    "package",
    [
        "io.camunda.zeebe.spring.client.annotation",
        "io.camunda.spring.client.annotation",
    ],
)
def test_camunda8_worker_and_variable_mapping(package: str) -> None:
    worker = f"""package app; import {package}.JobWorker; import {package}.Variable;
    class Worker {{ @JobWorker(type="charge") public void handle(@Variable(name="amount") int amount) {{}} }}"""
    xml = bpmn("""<serviceTask id="t"><extensionElements><z:taskDefinition type="charge"/>
       <z:ioMapping><z:input source="=order" target="amount"/><z:output source="=result" target="orderId"/></z:ioMapping>
    </extensionElements></serviceTask>""")
    batch, _, _ = analyze(
        {"Worker.java": worker, "p.bpmn": xml}, bpmn_profile="camunda8"
    )
    assert binding(batch).resolution.status == "RESOLVED"
    assert len(relations(batch, RelationKind.BPMN_INPUT_MAPPING)) == 1
    assert len(relations(batch, RelationKind.BPMN_OUTPUT_MAPPING)) == 1
    assert (
        relations(batch, RelationKind.BPMN_VARIABLE_BINDING)[0].resolution.status
        == "PARTIAL"
    )
    assert not relations(batch, RelationKind.BPMN_WRITES_VARIABLE)
    wrong, _, _ = analyze(
        {"Worker.java": worker, "p.bpmn": xml}, bpmn_profile="camunda7"
    )
    assert binding(wrong).resolution.status == "UNRESOLVED"
    assert any(
        isinstance(e, SourceAnalysis)
        and any(d.code == "bpmn.java.UNSUPPORTED_PROFILE" for d in e.diagnostics)
        for e in wrong.entities
    )


def test_camunda7_external_task_subscription() -> None:
    java = """package app;
    import org.camunda.bpm.client.spring.annotation.ExternalTaskSubscription;
    import org.camunda.bpm.client.task.ExternalTaskHandler;
    import org.camunda.bpm.client.task.ExternalTask;
    import org.camunda.bpm.client.task.ExternalTaskService;
    @ExternalTaskSubscription("charge") class Worker implements ExternalTaskHandler {
      public void execute(ExternalTask task, ExternalTaskService service) {task.getVariable("amount");}
    }"""
    batch, _, _ = analyze(
        {
            "Worker.java": java,
            "p.bpmn": bpmn('<serviceTask id="t" c:type="external" c:topic="charge"/>'),
        }
    )
    assert binding(batch).resolution.status == "RESOLVED"
    assert len(relations(batch, RelationKind.BPMN_READS_VARIABLE)) == 1


def test_missing_remote_worker_and_process_are_deferred_without_java_sources() -> None:
    batch, _, _ = analyze(
        {
            "p.bpmn": bpmn(
                '<serviceTask id="t" f:type="external-worker" f:topic="remote"/><callActivity id="c" calledElement="other-process"/>'
            )
        }
    )
    assert binding(batch).resolution.status == "UNRESOLVED"
    external = {
        e.selector.qualified_name
        for e in batch.entities
        if isinstance(e, ExternalReference)
    }
    assert external == {"bpmn.worker::remote", "bpmn.process::other-process"}


def test_conflicting_selectors_do_not_choose_one() -> None:
    batch, _, _ = analyze(
        {
            "Charge.java": DELEGATE,
            "p.bpmn": bpmn(
                '<serviceTask id="t" c:class="app.Charge" c:delegateExpression="${charge}"/>'
            ),
        }
    )
    assert binding(batch).resolution.status == "PARTIAL"
    assert binding(batch).resolution.target is None


def test_typed_variable_mappings_explicitly_keep_uncertain_lineage() -> None:
    xml = bpmn("""<serviceTask id="t" c:delegateExpression="${charge}"><extensionElements><c:inputOutput>
    <c:inputParameter name="amount">${order.total}</c:inputParameter>
    <c:outputParameter name="orderId">${result}</c:outputParameter>
    </c:inputOutput></extensionElements></serviceTask>""")
    batch, _, _ = analyze({"Charge.java": DELEGATE, "p.bpmn": xml})
    assert len(relations(batch, RelationKind.BPMN_READS_VARIABLE)) == 1
    assert len(relations(batch, RelationKind.BPMN_WRITES_VARIABLE)) == 1
    links = relations(batch, RelationKind.BPMN_VARIABLE_BINDING)
    assert len(links) == 2
    assert all(
        link.resolution.status == "PARTIAL" and link.certainty == Certainty.INFERRED
        for link in links
    )
    assert all(len(link.evidence) == 2 for link in links)


def test_dynamic_variable_and_namesake_methods_do_not_create_literal_lineage() -> None:
    java = DELEGATE.replace(
        'Object amount=e.getVariable("amount"); e.setVariable("result", amount);',
        'String name="amount"; Object amount=e.getVariable(name); this.getVariable("fake");',
    )
    java = java.replace("\n}", " Object getVariable(String name) {return null;}\n}")
    batch, _, _ = analyze(
        {
            "Charge.java": java,
            "p.bpmn": bpmn('<serviceTask id="t" c:class="app.Charge"/>'),
        }
    )
    assert len(relations(batch, RelationKind.BPMN_READS_VARIABLE)) == 1
    access = relations(batch, RelationKind.BPMN_READS_VARIABLE)[0]
    value = next(e for e in batch.entities if e.id == access.resolution.target.id)
    assert isinstance(value, Value) and value.value_kind == "UNKNOWN" and value.partial


def test_inherited_delegate_keeps_canonical_base_method_and_evidence_chain() -> None:
    base = DELEGATE.replace('@Component("charge")', "").replace(
        "class Charge", "class Base"
    )
    child = 'package app; import org.springframework.stereotype.Component; @Component("charge") class Child extends Base {}'
    batch, _, _ = analyze(
        {
            "Base.java": base,
            "Child.java": child,
            "p.bpmn": bpmn('<serviceTask id="t" c:class="app.Child"/>'),
        }
    )
    link = binding(batch)
    target = next(e for e in batch.entities if e.id == link.resolution.target.id)
    assert target.qualified_name == "app.Base.execute"
    paths = {e.id: e.path for e in batch.entities if isinstance(e, SourceFile)}
    assert {paths[e.source_range.source_file_id] for e in link.evidence} == {
        "Base.java",
        "Child.java",
        "p.bpmn",
    }


def test_incomplete_java_symbols_catalog_does_not_claim_unique_target() -> None:
    batch, _, _ = analyze(
        {
            "Charge.java": DELEGATE,
            "Broken.java": "class Broken {",
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
        },
        java_profile="symbols",
    )
    assert binding(batch).resolution.status == "PARTIAL"
    assert any(
        isinstance(e, SourceAnalysis)
        and any(d.code == "bpmn.java.PARTIAL_JAVA_CATALOG" for d in e.diagnostics)
        for e in batch.entities
    )


def test_delegate_to_sql_path_uses_existing_java_execution_facts() -> None:
    java = (
        IMPORTS
        + """import java.sql.Statement;
    @Component("charge") class Charge implements JavaDelegate {
      public void execute(DelegateExecution e) throws Exception {
        Statement db=(Statement)e.getVariable("db"); db.executeUpdate("update orders set state='done'");
      }
    }"""
    )
    batch, _, _ = analyze(
        {
            "Charge.java": java,
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
        },
        java_profile="execution",
    )
    method = binding(batch).resolution.target.id
    sql = relations(batch, RelationKind.EXECUTES_SQL)
    assert len(sql) == 1 and sql[0].source.id == method
    assert any(
        isinstance(e, SqlExecute) and e.id == sql[0].resolution.target.id
        for e in batch.entities
    )
    schema_only, _, _ = analyze(
        {
            "Charge.java": java,
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
        },
        java_profile="symbols",
    )
    assert not relations(schema_only, RelationKind.EXECUTES_SQL)


@pytest.mark.parametrize("profile", ["symbols", "calls"])
def test_catalog_reuses_existing_java_parse_and_canonical_ids(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    from code_crawler import java

    original = java.analyze
    calls = []

    def record(content):
        calls.append(content)
        return original(content)

    monkeypatch.setattr(java, "analyze", record)
    batch, _, _ = analyze(
        {
            "Charge.java": DELEGATE,
            "p.bpmn": bpmn('<serviceTask id="t" c:class="app.Charge"/>'),
        },
        java_profile=profile,
    )
    assert len(calls) == 1
    assert binding(batch).resolution.status == "RESOLVED"


def test_catalog_fingerprint_tracks_new_candidates_and_profile_changes() -> None:
    files = {
        "Charge.java": DELEGATE,
        "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
    }
    _, first, _ = analyze(files)
    _, same, _ = analyze(dict(reversed(list(files.items()))))
    _, changed, _ = analyze(
        {**files, "Other.java": DELEGATE.replace("Charge", "Other")}
    )
    _, profile, _ = analyze(files, bpmn_profile="camunda7")
    assert first.analysis_version == same.analysis_version
    assert (
        first.analysis_version != changed.analysis_version != profile.analysis_version
    )
    assert (
        next(s for s in first.scopes if s.key == "java.calls").fingerprint
        == next(s for s in profile.scopes if s.key == "java.calls").fingerprint
    )


def test_engine_profiles_reject_unknown_versions() -> None:
    with pytest.raises(ValueError, match="profile"):
        BpmnSourceAdapter("camunda99")


def test_disabled_job_worker_is_not_a_local_target() -> None:
    java = """package app; import io.camunda.spring.client.annotation.JobWorker;
    class Worker { @JobWorker(type="charge", enabled=false) void handle() {} }"""
    batch, _, _ = analyze(
        {
            "Worker.java": java,
            "p.bpmn": bpmn(
                '<serviceTask id="t"><extensionElements><z:taskDefinition type="charge"/></extensionElements></serviceTask>'
            ),
        }
    )
    assert binding(batch).resolution.status == "UNRESOLVED"


def test_named_injection_bean_alias() -> None:
    java = DELEGATE.replace(
        "import org.springframework.stereotype.Component;",
        "import jakarta.inject.Named;",
    ).replace('@Component("charge")', '@Named("charge")')
    batch, _, _ = analyze(
        {
            "Charge.java": java,
            "p.bpmn": bpmn('<serviceTask id="t" c:delegateExpression="${charge}"/>'),
        }
    )
    assert binding(batch).resolution.status == "RESOLVED"


def test_nul_variable_name_is_unknown_instead_of_invalid_postgres_text() -> None:
    java = DELEGATE.replace('e.getVariable("amount")', 'e.getVariable("\\0")')
    batch, _, _ = analyze(
        {
            "Charge.java": java,
            "p.bpmn": bpmn('<serviceTask id="t" c:class="app.Charge"/>'),
        }
    )
    read = relations(batch, RelationKind.BPMN_READS_VARIABLE)[0]
    value = next(e for e in batch.entities if e.id == read.resolution.target.id)
    assert value.value_kind == "UNKNOWN" and value.literal is None


@pytest.mark.parametrize("profile", ["flowable6", "flowable7"])
def test_flowable_process_mappings_and_unknown_io_extensions(profile: str) -> None:
    xml = bpmn("""<callActivity id="call" calledElement="remote"><extensionElements>
       <f:in source="order" target="amount"/><f:out source="result" target="orderId"/>
       <f:inputOutput><f:inputParameter name="unsupported">${value}</f:inputParameter></f:inputOutput>
    </extensionElements></callActivity>""")
    batch, _, _ = analyze({"p.bpmn": xml}, bpmn_profile=profile)
    assert len(relations(batch, RelationKind.BPMN_INPUT_MAPPING)) == 1
    assert len(relations(batch, RelationKind.BPMN_OUTPUT_MAPPING)) == 1
    assert not relations(batch, RelationKind.BPMN_VARIABLE_BINDING)


@pytest.mark.parametrize("files", [{}, {"pom.xml": "<project/>"}])
def test_non_bpmn_projects_do_not_build_java_binding_catalog(
    monkeypatch: pytest.MonkeyPatch, files: dict
) -> None:
    from code_crawler import bpmn_java_catalog

    def forbidden(*args, **kwargs):
        pytest.fail("Java binding catalog built without a BPMN document")

    monkeypatch.setattr(bpmn_java_catalog, "java_binding_catalog", forbidden)
    batch, _, _ = analyze({"Charge.java": DELEGATE, **files}, java_profile="symbols")
    assert not relations(batch, RelationKind.BPMN_HANDLER)


def test_numeric_namespace_references_still_request_java_catalog() -> None:
    xml = bpmn('<serviceTask id="t" c:class="app.Charge"/>').replace(
        BPMN, BPMN.replace("/", "&#47;")
    )
    batch, _, _ = analyze({"Charge.java": DELEGATE, "p.bpmn": xml})
    assert binding(batch).resolution.status == "RESOLVED"
