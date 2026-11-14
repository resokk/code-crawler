import asyncio
import hashlib
from uuid import UUID

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.javascript_adapter import (
    JavaScriptSourceAdapter,
    TypeScriptSourceAdapter,
)
from code_crawler.source_adapters import AdapterRegistry
from code_crawler.ucm import (
    EntityType,
    ExternalReference,
    Occurrence,
    Relation,
    RelationKind,
    SourceAnalysis,
    SourceFile,
    Symbol,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")


def source(path, text):
    content = text.encode()
    return SourceInput(
        SourceFile(
            repository_id=str(REPO),
            logical_key=path,
            id=logical_id(str(REPO), EntityType.SOURCE_FILE, path),
            name=path,
            path=path,
            language="javascript" if path.endswith((".js", ".jsx")) else "typescript",
            content_sha256=hashlib.sha256(content).hexdigest(),
        ),
        content,
    )


def analyze(files):
    async def run():
        sources = tuple(source(p, t) for p, t in files.items())
        registry = AdapterRegistry(
            (JavaScriptSourceAdapter(), TypeScriptSourceAdapter())
        )
        prepared = await registry.prepare(sources)
        results = await prepared(sources)
        entities = tuple(e for result in results for e in result.entities)
        UcmBatch(repository_id=REPO, entities=(*[s.file for s in sources], *entities))
        return results, entities, prepared

    return asyncio.run(run())


def test_import_call_evidence_and_negative_dependencies():
    results, entities, _ = analyze(
        {
            "src/a.ts": "export function greet(name: string): string { return name; }",
            "src/b.ts": 'import {greet as hello} from "./a.js"; export function run() { hello("x"); }',
        }
    )
    greet = next(e for e in entities if isinstance(e, Symbol) and e.name == "greet")
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert len(calls) == 1
    assert calls[0].resolution.target.id == greet.id
    assert (
        calls[0].evidence[0].source_range.source_file_id
        == source("src/b.ts", "").file.id
    )
    assert "src/a.ts" in results[1].dependencies
    assert "src/tsconfig.json" in results[1].dependencies


def test_overloads_generics_interfaces_and_type_only_import():
    _, entities, _ = analyze(
        {
            "a.ts": "export function f(x: string): string; export function f(x: number): number; export function f<T>(x: T): T {return x;} export interface Box<T> { value: T; get(): T; }",
            "b.ts": 'import type { f, Box } from "./a"; function run(x: Box<string>) { f("x"); }',
        }
    )
    overloads = [e for e in entities if isinstance(e, Symbol) and e.name == "f"]
    assert len(overloads) == len({s.id for s in overloads}) == 3
    assert all(s.signature for s in overloads)
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert calls and all(e.resolution.status == "UNRESOLVED" for e in calls)
    assert any(isinstance(e, Symbol) and e.name == "Box" for e in entities)
    assert (
        len(
            [
                e
                for e in entities
                if isinstance(e, Occurrence)
                and e.name == "f"
                and e.occurrence_kind == "DECLARATION"
            ]
        )
        == 3
    )


def test_dynamic_import_missing_module_and_shadowing():
    _, entities, _ = analyze(
        {
            "a.js": """
        import {remote} from "missing-package";
        function local() {}
        function run(local) { local(); import(path); remote(); }
    """
        }
    )
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert calls and all(e.resolution.status == "UNRESOLVED" for e in calls)
    external = [e for e in entities if isinstance(e, ExternalReference)]
    assert any("dynamic import" in e.reason for e in external)
    assert any("missing-package" in e.selector.qualified_name for e in external)


def test_http_fetch_axios_and_unknown_method():
    _, entities, _ = analyze(
        {
            "a.ts": """
        import client from "axios";
        fetch("https://example.com/users?q=1", {method: "POST"});
        fetch(`/users/${id}`);
        client.get("/orders");
        fetch("/unknown", {method});
        function hidden(fetch) { fetch("/shadowed"); }
    """
        }
    )
    http = [
        e
        for e in entities
        if isinstance(e, ExternalReference) and e.selector.kind == "HTTP"
    ]
    assert {(e.selector.method, e.selector.path) for e in http} == {
        ("POST", "/users"),
        ("GET", "/users/{dynamic}"),
        ("GET", "/orders"),
    }
    assert (
        next(e for e in http if e.selector.path == "/users").selector.service
        == "https://example.com"
    )
    assert "dynamic" in next(e for e in http if "dynamic" in e.selector.path).reason


def test_reexport_paths_tsx_and_idempotence():
    files = {
        "tsconfig.json": '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}',
        "src/a.ts": "export const f = <T,>(x: T) => x;",
        "src/index.ts": 'export {f as invoke} from "./a";',
        "ui.tsx": 'import {invoke} from "@/index"; export function View() { invoke(1); return <div/>; }',
    }
    results, entities, prepared = analyze(files)
    again, same, repeated = analyze(files)
    assert results == again and entities == same
    assert prepared.analysis_version == repeated.analysis_version
    f = next(e for e in entities if isinstance(e, Symbol) and e.name == "f")
    assert any(
        isinstance(e, Relation)
        and e.relation_kind == RelationKind.CALLS
        and e.resolution.target
        and e.resolution.target.id == f.id
        for e in entities
    )
    assert (
        "tsconfig.json" in next(r for r in results if r.path == "ui.tsx").dependencies
    )


def test_parser_errors_suppress_facts_and_json_is_metadata():
    _, entities, _ = analyze({"bad.ts": "function {", "package.json": "{}"})
    assert all(isinstance(e, SourceAnalysis) for e in entities)
    assert any(e.diagnostics for e in entities)


def test_namespace_reexport_imported_alias_and_ambiguous_star():
    _, entities, _ = analyze(
        {
            "a.ts": "export function f() {}",
            "b.ts": 'import {f} from "./a"; export {f as g};',
            "c.ts": 'import * as api from "./b"; function run() { api.g(); }',
            "d.ts": "export function f() {}",
            "ambiguous.ts": 'export * from "./a"; export * from "./d";',
            "consumer.ts": 'import {f} from "./ambiguous"; function ambiguous() {f();}',
        }
    )
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert sorted(e.resolution.status for e in calls) == ["RESOLVED", "UNRESOLVED"]


def test_mutated_binding_type_reexport_and_unparenthesized_arrow():
    _, entities, _ = analyze(
        {
            "a.js": "function f() {} f = unknown; function run() {f();} const g = f => f();",
            "a.ts": "export function f() {}",
            "types.ts": 'export type {f} from "./a";',
            "b.ts": 'import {f} from "./types"; function run() {f();}',
        }
    )
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert len(calls) == 3
    assert all(e.resolution.status == "UNRESOLVED" for e in calls)


def test_unicode_ranges_jsx_and_unsupported_config():
    results, entities, _ = analyze(
        {
            "view.jsx": "const имя = x => <p>{x}</p>;",
            "tsconfig.json": '{"extends":"../unavailable"}',
            "a.ts": 'import {missing} from "./";',
        }
    )
    declaration = next(e for e in entities if isinstance(e, Symbol) and e.name == "имя")
    assert (
        declaration.source_range.end.byte_column
        - declaration.source_range.start.byte_column
        == len("имя".encode())
    )
    assert next(
        e
        for e in entities
        if isinstance(e, SourceAnalysis)
        and e.source_file_id == source("tsconfig.json", "").file.id
    ).diagnostics
    assert "index.ts" in next(r for r in results if r.path == "a.ts").dependencies


def test_default_export_and_lexical_shadow_patterns():
    _, entities, _ = analyze(
        {
            "a.js": "function f() {} export default f;",
            "b.js": 'import f from "./a"; function run() {f();} function shadow({f}) {f();} function fallback(f = x) {f();} try {} catch(fetch) {fetch("/hidden");}',
        }
    )
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert sorted(e.resolution.status for e in calls) == [
        "RESOLVED",
        "UNRESOLVED",
        "UNRESOLVED",
    ]
    assert not any(
        isinstance(e, ExternalReference) and e.selector.kind == "HTTP" for e in entities
    )


def test_method_names_are_not_lexical_bindings_and_var_is_function_scoped():
    _, entities, _ = analyze(
        {
            "a.js": "class A {f() {} g() {f();}} function run() {if (x) {var f = () => 1;} f();}"
        }
    )
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert sorted(e.resolution.status for e in calls) == ["RESOLVED", "UNRESOLVED"]


def test_remote_reexports_stay_discoverable_and_config_does_not_guess_base_url():
    _, entities, _ = analyze(
        {
            "tsconfig.json": "{}",
            "api.ts": "export function f() {}",
            "a.ts": 'export {f} from "remote-package"; export * from "other-package"; import {f} from "api"; function run() {f();}',
        }
    )
    external = [e for e in entities if isinstance(e, ExternalReference)]
    assert {e.selector.qualified_name for e in external} == {
        "remote-package::f",
        "other-package::*",
        "api::f",
    }
    assert all(
        e.resolution.status == "UNRESOLVED"
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    )


def test_nested_anonymous_callback_does_not_claim_outer_runtime_call():
    _, entities, _ = analyze(
        {"a.js": "function f() {} function run() { const callbacks = [() => f()]; }"}
    )
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert len(calls) == 1
    owner = next(e for e in entities if e.id == calls[0].source.id)
    assert owner.name.startswith("<anonymous@")
    assert any(
        isinstance(e, Occurrence)
        and e.occurrence_kind == "CALL"
        and e.name == "f"
        and e.resolution == "RESOLVED"
        for e in entities
    )


def test_named_function_expression_recursion_and_generic_identity():
    _, entities, _ = analyze(
        {"a.ts": "const f = function recurse<T>(x: T): T {recurse(x); return x;};"}
    )
    f = next(e for e in entities if isinstance(e, Symbol) and e.name == "f")
    call = next(
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    )
    assert call.source.id == call.resolution.target.id == f.id
    assert f.signature.parameter_types[0].name == "T"
    assert f.signature.return_type.name == "T"


def test_type_only_reexport_survives_import_alias_chain():
    _, entities, _ = analyze(
        {
            "a.ts": "export function f() {}",
            "types.ts": 'export type {f} from "./a";',
            "barrel.ts": 'import {f as local} from "./types"; export {local as publicName};',
            "use.ts": 'import {publicName} from "./barrel"; function run() {publicName();}',
        }
    )
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert calls and all(e.resolution.status == "UNRESOLVED" for e in calls)


def test_for_of_bindings_shadow_outer_functions():
    _, entities, _ = analyze(
        {
            "a.js": "function f() {} function run(xs) {for (const f of xs) {f();} for (let {f} of xs) {f();} f();}"
        }
    )
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert sorted(e.resolution.status for e in calls) == [
        "RESOLVED",
        "UNRESOLVED",
        "UNRESOLVED",
    ]


def test_registered_js_ts_inventory_links_both_directions():
    results, entities, _ = analyze(
        {
            "a.js": 'import {g} from "./b"; export function f() {} function runJS() {g();}',
            "b.ts": 'import {f} from "./a"; export function g() {} function runTS() {f();}',
        }
    )
    calls = [
        e
        for e in entities
        if isinstance(e, Relation) and e.relation_kind == RelationKind.CALLS
    ]
    assert len(calls) == 2 and all(e.resolution.status == "RESOLVED" for e in calls)
    assert "b.ts" in results[0].dependencies and "a.js" in results[1].dependencies
