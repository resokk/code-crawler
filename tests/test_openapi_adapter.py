import asyncio
import json
import socket
from pathlib import Path

import pytest
from test_source_adapters import REPO, source

from code_crawler.ingestion import UcmBatch
from code_crawler.openapi_adapter import OpenApiSourceAdapter
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.ucm import ExternalReference, Relation, RelationKind, Symbol, Value


def analyze(files: dict[str, str]):
    async def run():
        sources = tuple(source(path, text, "openapi") for path, text in files.items())
        registry = AdapterRegistry((OpenApiSourceAdapter(),))
        prepared = await registry.prepare(sources)
        results = await prepared(sources)
        facts = tuple(e for result in results for e in result.entities)
        UcmBatch(repository_id=REPO, entities=(*[s.file for s in sources], *facts))
        return results, facts

    return asyncio.run(run())


def refs(facts):
    return [
        e
        for e in facts
        if isinstance(e, Relation) and e.relation_kind == RelationKind.OPENAPI_REF
    ]


@pytest.mark.parametrize("version", ["3.0.4", "3.1.1", "3.2.0"])
def test_versions_recursive_schema_and_operation(version):
    root = {
        "openapi": version,
        "info": {"title": "Пример", "version": "1"},
        "paths": {
            "/users/{id}": {
                "get": {
                    "operationId": "readUser",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Node"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Node"}
                                }
                            },
                        }
                    },
                    "security": [{"bearer": []}],
                    "callbacks": {
                        "event": {
                            "{$request.body#/url}": {
                                "post": {"responses": {"200": {"description": "ok"}}}
                            }
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "nullable": True},
                        "next": {"$ref": "#/components/schemas/Node"},
                    },
                    "allOf": [{"type": "object"}],
                    "discriminator": {"propertyName": "kind"},
                }
            },
            "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
        },
        "webhooks": {
            "created": {"post": {"responses": {"200": {"description": "ok"}}}}
        },
        "x-owner": {"name": "team"},
    }
    text = json.dumps(root, ensure_ascii=False)
    _, facts = analyze({"any-name.json": text})
    kinds = {e.symbol_kind for e in facts if isinstance(e, Symbol)}
    assert {
        "OPENAPI_DOCUMENT",
        "OPENAPI_OPERATION",
        "OPENAPI_PARAMETER",
        "OPENAPI_SCHEMA",
        "OPENAPI_FIELD",
        "OPENAPI_RESPONSE",
        "OPENAPI_BODY",
        "OPENAPI_MEDIA_TYPE",
        "OPENAPI_SECURITY",
        "OPENAPI_CALLBACK",
        "OPENAPI_WEBHOOK",
    } <= kinds
    assert len(refs(facts)) == 3 and all(
        r.resolution.status == "RESOLVED" for r in refs(facts)
    )
    assert all(r.evidence and r.coverage.status == "PARTIAL" for r in refs(facts))
    assert any(
        isinstance(e, Value) and e.name == "path" and e.literal == "/users/{id}"
        for e in facts
    )
    assert any(
        isinstance(e, Value) and e.name == "method" and e.literal == "GET"
        for e in facts
    )
    assert any(
        isinstance(e, Value) and e.name == "dialect" and e.literal == version
        for e in facts
    )
    reports = [e for e in facts if e.entity_type == "SOURCE_ANALYSIS"]
    assert any(
        d.code == "openapi.VENDOR_EXTENSION" for r in reports for d in r.diagnostics
    )
    if version.startswith("3.0"):
        assert not any(
            d.code == "openapi.DIALECT" and "nullable" in d.message
            for r in reports
            for d in r.diagnostics
        )
    else:
        assert any(
            d.code == "openapi.DIALECT" and "nullable" in d.message
            for r in reports
            for d in r.diagnostics
        )
    again = analyze({"any-name.json": text})[1]
    assert facts == again


def test_yaml_32_query_additional_operations_and_querystring():
    _, facts = analyze(
        {
            "api.yaml": """openapi: 3.2.0
paths:
  /search:
    query:
      parameters:
        - name: query
          in: querystring
          content:
            application/json:
              schema:
                type: [object, 'null']
    additionalOperations:
      COPY:
        responses:
          200:
            description: ok
"""
        }
    )
    methods = {e.literal for e in facts if isinstance(e, Value) and e.name == "method"}
    assert methods == {"QUERY", "COPY"}
    assert any(isinstance(e, Value) and e.literal == "querystring" for e in facts)
    assert any(
        isinstance(e, Symbol) and e.symbol_kind == "OPENAPI_PARAMETER" for e in facts
    )


def test_local_relative_missing_and_remote_refs_without_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("ambient I/O")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    _, facts = analyze(
        {
            "contracts/api.yaml": """openapi: 3.1.0
components:
  schemas:
    Local: {$ref: '../models.json#/$defs/Node'}
    Remote: {$ref: 'https://example.invalid/types.json#/Node'}
    Missing: {$ref: '../absent.yaml#/Node'}
""",
            "models.json": '{"$defs":{"Node":{"properties":{"self":{"$ref":"#/$defs/Node"}}}}}',
        }
    )
    assert len(refs(facts)) == 3
    assert sum(r.resolution.status == "RESOLVED" for r in refs(facts)) == 2
    assert any(
        r.resolution.status == "UNRESOLVED" and r.certainty == "UNKNOWN"
        for r in refs(facts)
    )
    assert any(
        isinstance(e, ExternalReference)
        and e.selector.qualified_name.startswith("openapi.ref::https:")
        for e in facts
    )
    assert not any(
        isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS for e in facts
    )


@pytest.mark.parametrize(
    "reference",
    [
        "../../secret.yaml#/x",
        "/etc/passwd",
        "%2fetc/passwd",
        "..%2f..%2fsecret",
        "bad\\file.yaml",
        "#/~2bad",
        ".",
        "%2e",
        "bad\nfile.yaml",
    ],
)
def test_unsafe_refs_remain_unresolved(reference):
    _, facts = analyze(
        {
            "api.json": json.dumps(
                {
                    "openapi": "3.1.0",
                    "components": {"schemas": {"Bad": {"$ref": reference}}},
                }
            )
        }
    )
    assert len(refs(facts)) == 1
    assert refs(facts)[0].resolution.status == "UNRESOLVED"


@pytest.mark.parametrize(
    "text",
    [
        "openapi: 3.1.0\nopenapi: 3.2.0",
        "openapi: 3.1.0\nx: &a {a: 1}\ny: *a",
        'openapi: 3.1.0\nx: !!python/object/apply:os.system ["echo unsafe"]',
        "openapi: [",
        "openapi: 3.1.0\nx: " + "[" * 70 + "0" + "]" * 70,
    ],
)
def test_malformed_unsafe_yaml_has_no_facts(text):
    _, facts = analyze({"api.yml": text})
    assert not any(isinstance(e, Symbol) for e in facts)
    assert any(
        d.code == "openapi.INVALID_DOCUMENT"
        for e in facts
        if e.entity_type == "SOURCE_ANALYSIS"
        for d in e.diagnostics
    )


def test_json_strict_and_unsupported_root():
    for text in (
        '{"openapi":"3.1.0","x":NaN}',
        '{"openapi":"3.1.0","openapi":"3.2.0"}',
        "{openapi: 3.1.0}",
        '{"openapi":"3.3.0"}',
        "{}",
    ):
        _, facts = analyze({"data.json": text})
        assert not any(isinstance(e, Symbol) for e in facts)
        assert all(
            c.status == "UNSUPPORTED"
            for e in facts
            if e.entity_type == "SOURCE_ANALYSIS"
            for c in e.capabilities
        )


def test_refs_in_examples_and_extensions_are_data():
    _, facts = analyze(
        {
            "api.json": json.dumps(
                {
                    "openapi": "3.1.0",
                    "components": {
                        "schemas": {
                            "X": {
                                "example": {"$ref": "missing.json"},
                                "x-metadata": {"$ref": "other.json"},
                            }
                        }
                    },
                }
            )
        }
    )
    assert not refs(facts)


def test_anchor_ambiguity_and_base_scope_deferred():
    _, facts = analyze(
        {
            "api.json": json.dumps(
                {
                    "openapi": "3.1.0",
                    "components": {
                        "schemas": {
                            "A": {"$anchor": "same"},
                            "B": {"$anchor": "same"},
                            "C": {"$ref": "#same"},
                            "D": {
                                "$id": "https://example.invalid/schema",
                                "$ref": "nested.json",
                            },
                        }
                    },
                }
            )
        }
    )
    assert any(
        r.resolution.status == "AMBIGUOUS" and len(r.resolution.candidates) == 2
        for r in refs(facts)
    )
    assert any(
        isinstance(e, ExternalReference) and "base-scope" in e.reason for e in facts
    )


def test_discriminator_mappings_and_escaped_pointer():
    _, facts = analyze(
        {
            "api.json": json.dumps(
                {
                    "openapi": "3.1.0",
                    "components": {
                        "schemas": {
                            "A/B": {"type": "object"},
                            "A": {"type": "object"},
                            "Union": {
                                "discriminator": {
                                    "propertyName": "kind",
                                    "mapping": {
                                        "a": "A",
                                        "b": "#/components/schemas/A~1B",
                                    },
                                }
                            },
                        }
                    },
                }
            )
        }
    )
    assert len(refs(facts)) == 2 and all(
        r.resolution.status == "RESOLVED" for r in refs(facts)
    )


def test_limits_and_wrong_shapes(monkeypatch):
    from code_crawler import openapi_adapter

    monkeypatch.setattr(openapi_adapter, "MAX_BYTES", 20)
    _, facts = analyze({"api.yaml": "openapi: 3.1.0\npaths: {}"})
    assert not any(isinstance(e, Symbol) for e in facts)
    monkeypatch.setattr(openapi_adapter, "MAX_BYTES", 4000000)
    monkeypatch.setattr(openapi_adapter, "MAX_NODES", 3)
    _, facts = analyze({"api.yaml": "openapi: 3.1.0\npaths: {}"})
    assert not any(isinstance(e, Symbol) for e in facts)


def test_old_dialect_and_schema_base_anchor_are_not_proven():
    _, facts = analyze(
        {
            "api.json": json.dumps(
                {
                    "openapi": "3.0.4",
                    "components": {
                        "schemas": {"A": {"$anchor": "a"}, "B": {"$ref": "#a"}}
                    },
                }
            )
        }
    )
    assert refs(facts)[0].resolution.status == "UNRESOLVED"
    _, facts = analyze(
        {
            "api.json": json.dumps(
                {
                    "openapi": "3.1.0",
                    "components": {
                        "schemas": {
                            "A": {"$id": "https://example.invalid/new", "$anchor": "a"},
                            "B": {"$ref": "#a"},
                        }
                    },
                }
            )
        }
    )
    assert refs(facts)[0].resolution.status == "UNRESOLVED"


def test_example_anchor_cannot_resolve_a_contract_reference():
    _, facts = analyze(
        {
            "api.json": json.dumps(
                {
                    "openapi": "3.1.0",
                    "components": {
                        "schemas": {
                            "A": {"example": {"$anchor": "hidden", "nullable": True}},
                            "B": {"$ref": "#hidden"},
                        }
                    },
                }
            )
        }
    )
    assert refs(facts)[0].resolution.status == "UNRESOLVED"
    assert not any(
        d.code == "openapi.DIALECT"
        for e in facts
        if e.entity_type == "SOURCE_ANALYSIS"
        for d in e.diagnostics
    )
