import asyncio
import hashlib
import json
from uuid import UUID

import pytest

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.openapi_adapter import OpenApiSourceAdapter
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.ucm import (
    Certainty,
    EntityType,
    ExternalReference,
    HttpSelector,
    Relation,
    RelationKind,
    SourceFile,
    SqlExecute,
    logical_id,
)

REPO = "00000000-0000-0000-0000-000000000006"
CONTROLLER = """package app; import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api") class Controller {
 @GetMapping("/users/{uid}") public User get(@PathVariable("uid") String id) {return null;}
}
class User {String name;}"""


def contract(path="/users/{id}", method="get", base="/api", extra=None):
    operation = {
        "parameters": [
            {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
        ],
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Person"}
                    }
                }
            }
        },
    }
    operation.update(extra or {})
    return json.dumps(
        {
            "openapi": "3.1.0",
            "servers": [{"url": base}],
            "paths": {path: {method: operation}},
            "components": {
                "schemas": {
                    "Person": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    }
                }
            },
        }
    )


def analyze(files, profile="calls"):
    sources = []
    for path, text in sorted(files.items()):
        content = text.encode()
        file = SourceFile(
            repository_id=REPO,
            logical_key=path,
            id=logical_id(REPO, EntityType.SOURCE_FILE, path),
            name=path,
            path=path,
            language="java" if path.endswith(".java") else "openapi",
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        sources.append(SourceInput(file, content))

    async def run():
        prepared = await AdapterRegistry(
            (JavaSourceAdapter(profile=profile), OpenApiSourceAdapter())
        ).prepare(tuple(sources))
        analyses = await prepared(tuple(sources))
        batch = UcmBatch(
            repository_id=UUID(REPO),
            entities=(
                *(s.file for s in sources),
                *(e for a in analyses for e in a.entities),
            ),
        )
        assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
        return batch, prepared, analyses

    return asyncio.run(run())


def links(batch, kind):
    return [
        e for e in batch.entities if isinstance(e, Relation) and e.relation_kind == kind
    ]


def handler(batch):
    result = links(batch, RelationKind.OPENAPI_HANDLER)
    assert len(result) == 1
    return result[0]


def test_class_prefix_and_path_parameter_aliases_keep_both_evidence_and_canonical_symbols():
    batch, _, _ = analyze(
        {"Controller.java": CONTROLLER, "api.json": contract()}, profile="orm"
    )
    binding = handler(batch)
    assert (
        binding.resolution.status == "RESOLVED"
        and binding.certainty == Certainty.INFERRED
    )
    target = next(e for e in batch.entities if e.id == binding.resolution.target.id)
    assert target.qualified_name == "app.Controller.get"
    files = {e.id: e.path for e in batch.entities if isinstance(e, SourceFile)}
    assert {files[e.source_range.source_file_id] for e in binding.evidence} == {
        "Controller.java",
        "api.json",
    }
    assert (
        links(batch, RelationKind.OPENAPI_JAVA_PARAMETER)[0].resolution.status
        == "PARTIAL"
    )
    dto = links(batch, RelationKind.OPENAPI_RESPONSE_DTO)[0]
    assert dto.resolution.status == "PARTIAL"
    assert (
        next(
            e for e in batch.entities if e.id == dto.resolution.candidates[0].id
        ).qualified_name
        == "app.User"
    )
    assert not any(
        isinstance(e, ExternalReference) and isinstance(e.selector, HttpSelector)
        for e in batch.entities
    )


def test_http_method_mismatch_does_not_bind():
    batch, _, _ = analyze(
        {
            "Controller.java": CONTROLLER.replace("GetMapping", "PostMapping"),
            "api.json": contract(),
        }
    )
    assert handler(batch).resolution.status == "UNRESOLVED"
    assert any(
        isinstance(e, ExternalReference)
        and isinstance(e.selector, HttpSelector)
        and e.selector.method == "GET"
        and e.selector.path == "/api/users/{id}"
        for e in batch.entities
    )


def test_duplicate_compatible_controllers_are_ambiguous():
    batch, _, _ = analyze(
        {
            "A.java": CONTROLLER.replace("class User {String name;}", ""),
            "B.java": CONTROLLER.replace("class Controller", "class OtherController"),
            "api.json": contract(),
        }
    )
    binding = handler(batch)
    assert (
        binding.resolution.status == "AMBIGUOUS"
        and len(binding.resolution.candidates) == 2
    )
    assert binding.certainty != Certainty.STATIC_PROVEN


@pytest.mark.parametrize("base", ["/wrong", "https://example.invalid/wrong"])
def test_known_server_prefix_is_not_discarded(base):
    batch, _, _ = analyze(
        {"Controller.java": CONTROLLER, "api.json": contract(base=base)}
    )
    assert handler(batch).resolution.status == "UNRESOLVED"


def test_captured_context_path_and_server_evidence():
    java = CONTROLLER.replace(
        '@RequestMapping("/api")', '@RequestMapping("/users")'
    ).replace('@GetMapping("/users/{uid}")', '@GetMapping("/{uid}")')
    batch, _, _ = analyze(
        {
            "Controller.java": java,
            "api.json": contract(base="/v1"),
            "src/main/resources/application.yaml": "server:\n  servlet:\n    context-path: /v1\n",
        }
    )
    binding = handler(batch)
    assert binding.resolution.status == "RESOLVED"
    file_ids = {e.id: e.path for e in batch.entities if isinstance(e, SourceFile)}
    assert "src/main/resources/application.yaml" in {
        file_ids[p.source_range.source_file_id] for p in binding.evidence
    }


@pytest.mark.parametrize(
    "java",
    [
        CONTROLLER.replace('"/users/{uid}"', "PATH"),
        CONTROLLER.replace('"/users/{uid}"', '"${route}"'),
        CONTROLLER.replace('"/users/{uid}"', '"/users/{uid:[0-9]+}"'),
    ],
)
def test_dynamic_or_regex_routes_do_not_become_resolved(java):
    batch, _, _ = analyze({"Controller.java": java, "api.json": contract()})
    assert handler(batch).resolution.status != "RESOLVED"


def test_constant_annotation_values_use_existing_static_constant_analysis():
    java = CONTROLLER.replace(
        '@GetMapping("/users/{uid}")',
        'static final String USERS="/users/" + "{uid}"; @GetMapping(USERS)',
    )
    batch, _, _ = analyze({"Controller.java": java, "api.json": contract()})
    assert handler(batch).resolution.status == "RESOLVED"


@pytest.mark.parametrize(
    "media,expected",
    [
        ("application/json", "RESOLVED"),
        ("application/*", "RESOLVED"),
        ("application/xml", "UNRESOLVED"),
        ("!application/json", "PARTIAL"),
    ],
)
def test_produces_constraints_are_checked(media, expected):
    java = CONTROLLER.replace(
        '@GetMapping("/users/{uid}")',
        '@GetMapping(path="/users/{uid}", produces="' + media + '")',
    )
    batch, _, _ = analyze({"Controller.java": java, "api.json": contract()})
    assert handler(batch).resolution.status == expected


def test_request_body_and_reactive_response_dto_use_signatures_not_schema_names():
    java = """package app; import org.springframework.web.bind.annotation.*;
    import org.springframework.http.ResponseEntity; import reactor.core.publisher.Mono;
    @RestController class Api { @PostMapping(path="/users", consumes="application/json", produces="application/json")
      public Mono<ResponseEntity<Output>> create(@RequestBody Input body) {return null;}
    } class Input {} class Output {}"""
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/users": {
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "object"}}}
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {"schema": {"type": "object"}}
                            }
                        }
                    },
                }
            }
        },
    }
    batch, _, _ = analyze({"Api.java": java, "api.json": json.dumps(spec)})
    assert handler(batch).resolution.status == "RESOLVED"
    for kind, name in (
        (RelationKind.OPENAPI_REQUEST_DTO, "app.Input"),
        (RelationKind.OPENAPI_RESPONSE_DTO, "app.Output"),
    ):
        binding = links(batch, kind)[0]
        assert binding.resolution.status == "PARTIAL"
        assert (
            next(
                e for e in batch.entities if e.id == binding.resolution.candidates[0].id
            ).qualified_name
            == name
        )


def test_media_mismatch_does_not_bind_request_body():
    java = CONTROLLER.replace(
        '@GetMapping("/users/{uid}")',
        '@GetMapping(path="/users/{uid}", consumes="application/xml")',
    )
    batch, _, _ = analyze(
        {
            "Controller.java": java,
            "api.json": contract(
                extra={
                    "requestBody": {
                        "content": {"application/json": {"schema": {"type": "object"}}}
                    }
                }
            ),
        }
    )
    assert handler(batch).resolution.status == "UNRESOLVED"


def test_feign_is_deferred_without_any_openapi_document():
    java = """package app; import org.springframework.cloud.openfeign.FeignClient;
    import org.springframework.web.bind.annotation.*;
    @FeignClient(name="loan-service", path="/v1") interface LoanClient {
      @GetMapping("/loans/{id}") Loan get(@PathVariable("id") String id);
    } class Loan {}"""
    batch, _, _ = analyze({"LoanClient.java": java}, profile="symbols")
    refs = [
        e
        for e in batch.entities
        if isinstance(e, ExternalReference) and isinstance(e.selector, HttpSelector)
    ]
    assert len(refs) == 1
    assert (
        refs[0].selector.service == "loan-service" and refs[0].selector.method == "GET"
    )
    assert (
        refs[0].selector.path == "/v1/loans/{id}" and refs[0].resolution == "UNRESOLVED"
    )
    assert refs[0].certainty == Certainty.UNKNOWN
    assert not links(batch, RelationKind.OPENAPI_HANDLER)


def test_feign_url_prefix_and_no_local_controller_binding():
    java = """package app; import org.springframework.cloud.openfeign.FeignClient; import org.springframework.web.bind.annotation.*;
    @FeignClient(name="loans", url="https://loan.invalid/base", path="/api") interface Client {
      @GetMapping("/users/{id}") String get(@PathVariable("id") String id);
    }"""
    batch, _, _ = analyze({"Client.java": java, "api.json": contract()})
    assert handler(batch).resolution.status == "UNRESOLVED"
    assert any(
        isinstance(e, ExternalReference)
        and isinstance(e.selector, HttpSelector)
        and e.selector.path == "/base/api/users/{id}"
        for e in batch.entities
    )


def test_inherited_interface_method_mapping_targets_concrete_method():
    interface = """package app; import org.springframework.web.bind.annotation.*;
    interface Api { @GetMapping("/users/{uid}") User get(@PathVariable("uid") String uid); }"""
    java = (
        CONTROLLER.replace('@GetMapping("/users/{uid}") ', "")
        .replace("class Controller {", "class Controller implements Api {")
        .replace('@PathVariable("uid") ', "")
    )
    batch, _, _ = analyze(
        {"Api.java": interface, "Controller.java": java, "api.json": contract()}
    )
    assert handler(batch).resolution.status == "RESOLVED"
    target = next(
        e for e in batch.entities if e.id == handler(batch).resolution.target.id
    )
    assert target.qualified_name == "app.Controller.get"


def test_fake_unqualified_annotations_are_not_spring_routes():
    java = CONTROLLER.replace("import org.springframework.web.bind.annotation.*;", "")
    batch, _, _ = analyze({"Controller.java": java, "api.json": contract()})
    assert handler(batch).resolution.status == "UNRESOLVED"


def test_trailing_slash_is_not_silently_normalized():
    batch, _, _ = analyze(
        {"Controller.java": CONTROLLER, "api.json": contract(path="/users/{id}/")}
    )
    assert handler(batch).resolution.status == "UNRESOLVED"


def test_incomplete_java_symbols_catalog_keeps_candidate_partial():
    batch, _, _ = analyze(
        {
            "Controller.java": CONTROLLER,
            "Broken.java": "class Broken {",
            "api.json": contract(),
        },
        profile="symbols",
    )
    assert handler(batch).resolution.status == "PARTIAL"


def test_java_parser_is_reused_by_http_and_bpmn_catalogs(monkeypatch):
    from code_crawler import java

    original = java.analyze
    calls = []

    def record(content):
        calls.append(content)
        return original(content)

    monkeypatch.setattr(java, "analyze", record)
    batch, _, _ = analyze({"Controller.java": CONTROLLER, "api.json": contract()})
    assert handler(batch).resolution.status == "RESOLVED"
    assert len(calls) == 1


def test_http_catalog_changes_invalidate_openapi_scope():
    files = {"Controller.java": CONTROLLER, "api.json": contract()}
    _, first, _ = analyze(files)
    _, same, _ = analyze(dict(reversed(list(files.items()))))
    _, changed, _ = analyze(
        {**files, "Controller.java": CONTROLLER.replace("GetMapping", "PostMapping")}
    )
    assert first.analysis_version == same.analysis_version
    assert first.analysis_version != changed.analysis_version


def sql_controller() -> str:
    java = (
        CONTROLLER.replace(
            "import org.springframework.web.bind.annotation.*;",
            "import org.springframework.web.bind.annotation.RestController; import org.springframework.web.bind.annotation.RequestMapping; import org.springframework.web.bind.annotation.GetMapping; import org.springframework.web.bind.annotation.PathVariable; import java.sql.Statement;",
        )
        .replace("class Controller {", "class Controller { Service service;")
        .replace("return null;", "return service.load(id);")
    )
    java += """ class Service { Statement db;
       public User load(String id) {db.executeUpdate("update users set active=true"); return null;}
    }"""
    return java


def test_handler_service_sql_path_uses_existing_java_analyzers():
    java = sql_controller()
    batch, _, _ = analyze(
        {"Controller.java": java, "api.json": contract()}, profile="execution"
    )
    method_id = handler(batch).resolution.target.id
    calls = [r for r in links(batch, RelationKind.CALLS) if r.source.id == method_id]
    assert any(r.resolution.target for r in calls)
    callees = {r.resolution.target.id for r in calls if r.resolution.target}
    sql = links(batch, RelationKind.EXECUTES_SQL)
    assert len(sql) == 1 and sql[0].source.id in callees
    assert any(
        isinstance(e, SqlExecute) and e.id == sql[0].resolution.target.id
        for e in batch.entities
    )


def test_media_parameter_values_remain_case_sensitive():
    java = CONTROLLER.replace(
        '@GetMapping("/users/{uid}")',
        '@GetMapping(path="/users/{uid}", produces="application/json;profile=Admin")',
    )
    spec = contract(
        extra={
            "responses": {
                "200": {
                    "content": {
                        "application/json;profile=admin": {"schema": {"type": "object"}}
                    }
                }
            }
        }
    )
    batch, _, _ = analyze({"Controller.java": java, "api.json": spec})
    assert handler(batch).resolution.status == "UNRESOLVED"


def test_feign_default_methods_do_not_create_outgoing_requests():
    java = """package app; import org.springframework.cloud.openfeign.FeignClient; import org.springframework.web.bind.annotation.*;
    @FeignClient(name="loans") interface Client { @GetMapping("/local") default String helper() {return "local";} }"""
    batch, _, _ = analyze({"Client.java": java}, profile="symbols")
    assert not any(
        isinstance(e, ExternalReference) and isinstance(e.selector, HttpSelector)
        for e in batch.entities
    )


@pytest.mark.parametrize(
    "condition,required,enum,expected",
    [
        ("mode=full", True, ["full"], "RESOLVED"),
        ("mode=full", True, ["summary"], "UNRESOLVED"),
        ("mode=full", False, [], "PARTIAL"),
        ("!mode", False, [], "PARTIAL"),
    ],
)
def test_request_parameter_constraints(condition, required, enum, expected):
    java = CONTROLLER.replace(
        '@GetMapping("/users/{uid}")',
        f'@GetMapping(path="/users/{{uid}}", params="{condition}")',
    )
    spec = contract(
        extra={
            "parameters": [
                {
                    "name": "mode",
                    "in": "query",
                    "required": required,
                    "schema": {"type": "string", "enum": enum},
                }
            ]
        }
    )
    batch, _, _ = analyze({"Controller.java": java, "api.json": spec})
    assert handler(batch).resolution.status == expected


def test_conflicting_context_profiles_remain_partial():
    batch, _, _ = analyze(
        {
            "Controller.java": CONTROLLER,
            "api.json": contract(),
            "application-prod.yml": "server.servlet.context-path: /other\n",
        }
    )
    assert handler(batch).resolution.status != "RESOLVED"


def test_dynamic_server_keeps_only_partial_local_candidate():
    batch, _, _ = analyze(
        {
            "Controller.java": CONTROLLER,
            "api.json": contract(base="https://api.invalid/{version}"),
        }
    )
    assert handler(batch).resolution.status != "RESOLVED"


def test_head_mapping_and_request_method_enum():
    java = CONTROLLER.replace(
        '@GetMapping("/users/{uid}")',
        '@RequestMapping(path="/users/{uid}", method=RequestMethod.GET)',
    )
    batch, _, _ = analyze(
        {"Controller.java": java, "api.json": contract(method="head")}
    )
    assert handler(batch).resolution.status == "RESOLVED"


def test_external_parameter_fragment_keeps_typed_alias():
    root = json.loads(contract())
    root["paths"]["/users/{id}"]["get"]["parameters"] = [{"$ref": "./parameter.json"}]
    batch, _, _ = analyze(
        {
            "Controller.java": CONTROLLER,
            "api.json": json.dumps(root),
            "parameter.json": json.dumps(
                {
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                }
            ),
        }
    )
    assert handler(batch).resolution.status == "RESOLVED"
    assert len(links(batch, RelationKind.OPENAPI_JAVA_PARAMETER)) == 1


def test_missing_java_dto_is_not_matched_by_openapi_schema_name():
    java = CONTROLLER.replace("public User get", "public Unknown get").replace(
        "class User {String name;}", "class Person {}"
    )
    batch, _, _ = analyze({"Controller.java": java, "api.json": contract()})
    assert handler(batch).resolution.status == "RESOLVED"
    assert not links(batch, RelationKind.OPENAPI_RESPONSE_DTO)


@pytest.mark.parametrize(
    "declaration,has_dto", [("public User", False), ("@ResponseBody public User", True)]
)
def test_plain_controller_model_is_not_assumed_to_be_a_response_body(
    declaration, has_dto
):
    java = (
        CONTROLLER.replace(
            "import org.springframework.web.bind.annotation.*;",
            "import org.springframework.web.bind.annotation.*; import org.springframework.stereotype.Controller;",
        )
        .replace("@RestController", "@Controller")
        .replace("class Controller", "class UserController")
        .replace("public User", declaration)
    )
    batch, _, _ = analyze({"Controller.java": java, "api.json": contract()})
    assert handler(batch).resolution.status == "RESOLVED"
    assert bool(links(batch, RelationKind.OPENAPI_RESPONSE_DTO)) == has_dto


@pytest.mark.parametrize(
    "mapping", ['@RequestMapping(path="/x", method=UNKNOWN)', '@GetMapping("/x")']
)
def test_unknown_feign_method_or_url_does_not_invent_an_http_selector(mapping):
    url = ', url="${service.url}"' if "GetMapping" in mapping else ""
    java = f"""package app; import org.springframework.cloud.openfeign.FeignClient; import org.springframework.web.bind.annotation.*;
    @FeignClient(name="loans"{url}) interface Client {{ {mapping} String get(); }}"""
    batch, _, _ = analyze({"Client.java": java})
    refs = [e for e in batch.entities if isinstance(e, ExternalReference)]
    assert refs and not any(isinstance(e.selector, HttpSelector) for e in refs)
