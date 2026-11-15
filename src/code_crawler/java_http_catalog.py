"""Spring/Feign declarations from the existing canonical Java AST and symbols."""

import hashlib
import itertools
import json
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from tree_sitter import Node

from code_crawler import java
from code_crawler.incremental import SourceInput
from code_crawler.java_calls import _modifiers
from code_crawler.java_catalog import JavaDeclarationCatalog, JavaType
from code_crawler.java_symbols import JavaSymbolsResult
from code_crawler.jpa_catalog import arguments, literal_string
from code_crawler.source_adapters import AdapterCatalog
from code_crawler.ucm import ContractModel, Evidence, Symbol, Text

CATALOG_KEY = "java.http.routes"
VERSION = "java.http/1"
WEB = "org.springframework.web.bind.annotation."
FEIGN = "org.springframework.cloud.openfeign.FeignClient"
CONTROLLERS = frozenset(
    (WEB + "RestController", "org.springframework.stereotype.Controller")
)
MAPPINGS = {
    WEB + "RequestMapping": None,
    **{
        WEB + m.title() + "Mapping": m
        for m in ("GET", "POST", "PUT", "DELETE", "PATCH")
    },
}
PARAMETERS = {
    WEB + a: kind
    for a, kind in (
        ("PathVariable", "path"),
        ("RequestParam", "query"),
        ("RequestHeader", "header"),
        ("CookieValue", "cookie"),
        ("RequestBody", "body"),
    )
}
WRAPPERS = frozenset(
    (
        "org.springframework.http.ResponseEntity",
        "org.springframework.http.HttpEntity",
        "reactor.core.publisher.Mono",
        "reactor.core.publisher.Flux",
        "java.util.List",
        "java.util.Set",
        "java.util.Collection",
        "java.util.Optional",
    )
)
KNOWN = frozenset(
    (
        *CONTROLLERS,
        *MAPPINGS,
        *PARAMETERS,
        *WRAPPERS,
        "java.lang.String",
        "java.lang.Object",
        "java.lang.Integer",
        "java.lang.Long",
        WEB + "RequestMethod",
        WEB + "ResponseBody",
        FEIGN,
        "feign.RequestLine",
    )
)
HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE")
MAX_METHOD_ROUTES = 128


class HttpParameter(ContractModel):
    kind: Literal["path", "query", "header", "cookie", "body"]
    name: Text | None = None
    symbol: Symbol
    types: tuple[Symbol, ...] = ()
    evidence: tuple[Evidence, ...]


class JavaHttpRoute(ContractModel):
    kind: Literal["SERVER", "CLIENT"]
    registration: Text
    symbol: Symbol
    path: Text | None = None
    methods: tuple[Text, ...] = ()
    consumes: tuple[Text, ...] = ()
    produces: tuple[Text, ...] = ()
    params: tuple[Text, ...] = ()
    headers: tuple[Text, ...] = ()
    service: Text | None = None
    parameters: tuple[HttpParameter, ...] = ()
    responses: tuple[Symbol, ...] = ()
    evidence: tuple[Evidence, ...]
    incomplete: tuple[Text, ...] = ()


class HttpIssue(ContractModel):
    code: Text
    message: Text
    evidence: Evidence


class JavaHttpCatalog(AdapterCatalog):
    routes: tuple[JavaHttpRoute, ...] = ()
    issues: tuple[HttpIssue, ...] = ()
    failed_paths: tuple[Text, ...] = ()


@dataclass(frozen=True)
class _Mapping:
    paths: tuple[str | None, ...] = ("",)
    methods: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    params: tuple[str, ...] = ()
    headers: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    incomplete: tuple[str, ...] = ()


def join_path(*parts: str) -> str:
    """Join declared path prefixes without collapsing interior or trailing slashes."""
    result = ""
    for part in parts:
        if part:
            result = result.rstrip("/") + "/" + part.lstrip("/")
    return result or "/"


def mentions_http(sources: tuple[SourceInput, ...]) -> bool:
    """Skip the binding catalog when no supported annotation namespace is present."""
    tokens = (
        WEB.encode(),
        b"org.springframework.stereotype.Controller",
        FEIGN.encode(),
        b"feign.RequestLine",
    )
    return any(any(token in source.content for token in tokens) for source in sources)


class _Collector(JavaDeclarationCatalog):
    def __init__(
        self, pairs: tuple[tuple[SourceInput, JavaSymbolsResult], ...]
    ) -> None:
        super().__init__(pairs, KNOWN, "java.http", VERSION)
        self.issues: list[HttpIssue] = []

    def text(self, node: Node | None, owner: JavaType) -> str | None:
        if node is None or node.type not in (
            "string_literal",
            "identifier",
            "field_access",
            "binary_expression",
            "parenthesized_expression",
        ):
            return None
        constants = owner.unit.result._extractor.parsed._constant_scopes.get(
            owner.symbol.qualified_name, {}
        )
        try:
            value = literal_string(node, constants)
        except (ValueError, RecursionError):
            return None
        return value if value is not None and "\0" not in value else None

    def strings(
        self, args: dict, key: str, owner: JavaType
    ) -> tuple[tuple[str, ...], bool]:
        node = args.get(key)
        if node is None:
            return (), True
        children = (
            node.named_children
            if node.type == "element_value_array_initializer"
            else (node,)
        )
        values = tuple(self.text(n, owner) for n in children)
        return tuple(v for v in values if v is not None), all(
            v is not None for v in values
        )

    def mapping(
        self, annotations: tuple[tuple[str, Node], ...], owner: JavaType
    ) -> _Mapping | None:
        found = [(name, node) for name, node in annotations if name in MAPPINGS]
        if not found:
            return None
        name, node = found[0]
        args = arguments(node)
        incomplete = (
            ["Multiple mapping annotations on one declaration."]
            if len(found) > 1
            else []
        )
        path_values = [key for key in ("path", "value") if key in args]
        paths, known = (
            self.strings(args, path_values[0], owner) if path_values else (("",), True)
        )
        if len(path_values) == 2:
            other, other_known = self.strings(args, path_values[1], owner)
            if not other_known or other != paths:
                known = False
        if not known:
            paths = (None,)
            incomplete.append("Dynamic or conflicting path/value annotation.")
        paths = paths or ("",)
        method = MAPPINGS[name]
        methods = (method,) if method else ()
        if method is None and "method" in args:
            value = args["method"]
            nodes = (
                value.named_children
                if value.type == "element_value_array_initializer"
                else (value,)
            )
            methods_list = []
            for expression in nodes:
                text = java._text(expression)
                prefix, _, verb = text.rpartition(".")
                qualified = self.qualify(prefix, owner) if prefix else None
                static = any(
                    java._text(n).strip()
                    in (
                        f"import static {WEB}RequestMethod.{text};",
                        f"import static {WEB}RequestMethod.*;",
                    )
                    for n in owner.unit.result._extractor.parsed._tree.root_node.named_children
                    if n.type == "import_declaration"
                )
                if verb in HTTP_METHODS and (
                    qualified == WEB + "RequestMethod" or not prefix and static
                ):
                    methods_list.append(verb)
                else:
                    incomplete.append("Unresolved RequestMethod annotation value.")
            methods = tuple(sorted(set(methods_list)))
        values = {}
        for key in ("consumes", "produces", "params", "headers"):
            values[key], known = self.strings(args, key, owner)
            if not known:
                incomplete.append("Dynamic " + key + " condition.")
        return _Mapping(
            paths=paths,
            methods=methods,
            **values,
            evidence=(self.evidence(owner, node, "spring.mapping"),),
            incomplete=tuple(incomplete),
        )

    def hierarchy(
        self, owner: JavaType, seen: frozenset[str] = frozenset()
    ) -> tuple[JavaType, ...]:
        if owner.symbol.id in seen or len(seen) >= 64:
            return ()
        result = [owner]
        for name in self.bases(owner):
            parents = self.types.get(name, ())
            if len(parents) > 1:
                self.issues.append(
                    HttpIssue(
                        code="AMBIGUOUS_BASE",
                        message="Multiple local definitions of an inherited type.",
                        evidence=self.evidence(owner, owner.node, "spring.inheritance"),
                    )
                )
            if len(parents) == 1:
                result.extend(self.hierarchy(parents[0], seen | {owner.symbol.id}))
        return tuple({item.symbol.id: item for item in result}.values())

    def dto(self, node: Node | None, owner: JavaType) -> tuple[Symbol, ...]:
        if node is None:
            return ()
        if node.type == "array_type":
            return self.dto(node.child_by_field_name("element"), owner)
        if node.type == "generic_type":
            head = node.named_children[0]
            container = self.qualify(java._text(head), owner)
            args = next(
                (n for n in node.named_children if n.type == "type_arguments"), None
            )
            if (
                container in WRAPPERS
                and args is not None
                and len(args.named_children) == 1
            ):
                return self.dto(args.named_children[0], owner)
            return ()
        name = self.qualify(java._text(node), owner)
        return tuple(t.symbol for t in self.types.get(name, ()))

    def parameters(
        self,
        symbol: Symbol,
        node: Node,
        owner: JavaType,
        annotation_method: Node,
        annotation_owner: JavaType,
    ) -> tuple[HttpParameter, ...]:
        actual = node.child_by_field_name("parameters")
        inherited = annotation_method.child_by_field_name("parameters")
        params = (
            [n for n in actual.named_children if n.type == "formal_parameter"]
            if actual
            else []
        )
        inherited_params = (
            [n for n in inherited.named_children if n.type == "formal_parameter"]
            if inherited
            else []
        )
        declared = {
            s.logical_key: s
            for s in owner.unit.result.declared
            if isinstance(s, Symbol)
        }
        result = []
        for index, param in enumerate(params):
            canonical = declared.get(symbol.logical_key + f":parameter:{index}")
            if canonical is None:
                continue
            annotations = self.annotations(param, owner)
            ann_owner = owner
            if not any(name in PARAMETERS for name, _ in annotations) and len(
                params
            ) == len(inherited_params):
                annotations = self.annotations(
                    inherited_params[index], annotation_owner
                )
                ann_owner = annotation_owner
            for name, annotation in annotations:
                if name not in PARAMETERS:
                    continue
                args = arguments(annotation)
                explicit = args.get("name") or args.get("value")
                key = (
                    self.text(explicit, ann_owner)
                    if explicit is not None
                    else canonical.name
                )
                result.append(
                    HttpParameter(
                        kind=PARAMETERS[name],
                        name=key if key and key.strip() else None,
                        symbol=canonical,
                        types=self.dto(param.child_by_field_name("type"), owner),
                        evidence=(
                            self.evidence(ann_owner, annotation, "spring.parameter"),
                            self.evidence(owner, param, "java.parameter.type"),
                        ),
                    )
                )
        return tuple(result)

    def signature_key(self, method: Symbol, owner: JavaType) -> tuple:
        return method.name, tuple(
            self.qualify(t.name, owner) or t.name
            for t in method.signature.parameter_types
        )

    def collect(self) -> tuple[JavaHttpRoute, ...]:
        routes = []
        for owners in self.types.values():
            for owner in owners:
                annotations = self.annotations(owner.node, owner)
                feign = next(
                    (node for name, node in annotations if name == FEIGN), None
                )
                hierarchy = self.hierarchy(owner)
                controller = any(
                    name in CONTROLLERS
                    for base in hierarchy
                    for name, _ in self.annotations(base.node, base)
                )
                if feign is None and (
                    not controller
                    or owner.node.type
                    not in ("class_declaration", "record_declaration")
                    or "abstract" in _modifiers(owner.node)
                ):
                    continue
                class_mappings = [
                    (m, base)
                    for base in hierarchy
                    if (m := self.mapping(self.annotations(base.node, base), base))
                    is not None
                ]
                class_mapping, _class_owner = (
                    class_mappings[0] if class_mappings else (_Mapping(), owner)
                )
                if (
                    _class_owner.symbol.id != owner.symbol.id
                    and len({m for m, _ in class_mappings}) > 1
                ):
                    class_mapping = _Mapping(
                        **{
                            **class_mapping.__dict__,
                            "incomplete": (
                                *class_mapping.incomplete,
                                "Ambiguous inherited class mappings.",
                            ),
                        }
                    )
                controller_proof = tuple(
                    self.evidence(base, annotation, "spring.controller.marker")
                    for base in hierarchy
                    for name, annotation in self.annotations(base.node, base)
                    if name in CONTROLLERS
                )
                service, client_base, client_incomplete = None, "", []
                client_proof = ()
                if feign is not None:
                    args = arguments(feign)
                    names = [
                        self.text(args[k], owner)
                        for k in ("name", "value")
                        if k in args
                    ]
                    service = names[0] if names and len(set(names)) == 1 else None
                    prefix = self.text(args["path"], owner) if "path" in args else ""
                    url = self.text(args["url"], owner) if "url" in args else ""
                    client_base = prefix or ""
                    if (
                        prefix is None
                        or url is None
                        or service is None
                        or service
                        and any(t in service for t in ("${", "#{"))
                    ):
                        service = (
                            None
                            if service and any(t in service for t in ("${", "#{"))
                            else service
                        )
                        client_incomplete.append("Dynamic Feign service, path or URL.")
                    if url:
                        try:
                            uri = urlsplit(url)
                            if (
                                uri.scheme not in ("http", "https")
                                or not uri.netloc
                                or uri.query
                                or uri.fragment
                                or "{" in url
                            ):
                                raise ValueError("Unsupported Feign base URL")
                            client_base = join_path(uri.path, client_base)
                            service = service or uri.netloc.rsplit("@", 1)[-1]
                        except ValueError:
                            client_incomplete.append("Unsupported Feign base URL.")
                    client_proof = (self.evidence(owner, feign, "feign.client"),)
                effective = {}
                for base in reversed(hierarchy):
                    for method, node in self.methods.get(base.symbol.logical_key, ()):
                        signature = self.signature_key(method, base)
                        effective[signature] = (method, node, base)
                for symbol, node, defining in effective.values():
                    if (
                        feign is not None
                        and (
                            {"static", "private"} & _modifiers(node)
                            or node.child_by_field_name("body") is not None
                        )
                        or feign is None
                        and node.child_by_field_name("body") is None
                    ):
                        continue
                    method_mapping = self.mapping(
                        self.annotations(node, defining), defining
                    )
                    ann_node, ann_owner = node, defining
                    if method_mapping is None:
                        inherited = []
                        for base in hierarchy:
                            for original, original_node in self.methods.get(
                                base.symbol.logical_key, ()
                            ):
                                if self.signature_key(
                                    original, base
                                ) == self.signature_key(symbol, defining):
                                    candidate = self.mapping(
                                        self.annotations(original_node, base), base
                                    )
                                    if candidate:
                                        inherited.append(
                                            (candidate, original_node, base)
                                        )
                        if inherited:
                            method_mapping, ann_node, ann_owner = inherited[0]
                            if len({m for m, _, _ in inherited}) > 1:
                                method_mapping = _Mapping(
                                    **{
                                        **method_mapping.__dict__,
                                        "incomplete": (
                                            *method_mapping.incomplete,
                                            "Ambiguous inherited method mappings.",
                                        ),
                                    }
                                )
                    native = next(
                        (
                            n
                            for name, n in self.annotations(node, defining)
                            if name == "feign.RequestLine"
                        ),
                        None,
                    )
                    if (
                        feign is not None
                        and native is not None
                        and method_mapping is None
                    ):
                        value = self.text(arguments(native).get("value"), defining)
                        parts = value.split(maxsplit=1) if value else ()
                        if len(parts) == 2 and parts[0] in HTTP_METHODS:
                            method_mapping = _Mapping(
                                paths=(parts[1],),
                                methods=(parts[0],),
                                evidence=(
                                    self.evidence(
                                        defining, native, "feign.request-line"
                                    ),
                                ),
                            )
                        else:
                            method_mapping = _Mapping(
                                paths=(None,),
                                incomplete=("Dynamic Feign RequestLine.",),
                                evidence=(
                                    self.evidence(
                                        defining, native, "feign.request-line"
                                    ),
                                ),
                            )
                    if method_mapping is None:
                        continue
                    methods = tuple(
                        sorted(set(class_mapping.methods) | set(method_mapping.methods))
                    )
                    if (
                        feign is not None
                        and not methods
                        and not any(
                            "RequestMethod" in reason
                            for reason in (
                                *class_mapping.incomplete,
                                *method_mapping.incomplete,
                            )
                        )
                    ):
                        methods = ("GET",)
                    parameters = self.parameters(
                        symbol, node, defining, ann_node, ann_owner
                    )
                    response_body = (
                        feign is not None
                        or any(
                            name in (WEB + "RestController", WEB + "ResponseBody")
                            for base in hierarchy
                            for name, _ in self.annotations(base.node, base)
                        )
                        or any(
                            name == WEB + "ResponseBody"
                            for name, _ in (
                                *self.annotations(node, defining),
                                *self.annotations(ann_node, ann_owner),
                            )
                        )
                    )
                    return_node = node.child_by_field_name("type")
                    cursor = return_node
                    while cursor is not None and cursor.type == "generic_type":
                        container = self.qualify(
                            java._text(cursor.named_children[0]), defining
                        )
                        if container in (
                            "org.springframework.http.ResponseEntity",
                            "org.springframework.http.HttpEntity",
                        ):
                            response_body = True
                            break
                        args = next(
                            (
                                c
                                for c in cursor.named_children
                                if c.type == "type_arguments"
                            ),
                            None,
                        )
                        cursor = (
                            args.named_children[0]
                            if container in WRAPPERS
                            and args
                            and len(args.named_children) == 1
                            else None
                        )
                    responses = self.dto(return_node, defining) if response_body else ()
                    incomplete = (
                        *class_mapping.incomplete,
                        *method_mapping.incomplete,
                        *client_incomplete,
                    )
                    combos = itertools.product(
                        class_mapping.paths, method_mapping.paths
                    )
                    for index, (prefix, suffix) in enumerate(combos):
                        if index == MAX_METHOD_ROUTES:
                            self.issues.append(
                                HttpIssue(
                                    code="ROUTE_LIMIT",
                                    message="Mapping path product exceeds 128 routes; candidates are incomplete.",
                                    evidence=self.evidence(
                                        defining, node, "spring.route.limit"
                                    ),
                                )
                            )
                            break
                        path = (
                            join_path(client_base, prefix, suffix)
                            if prefix is not None and suffix is not None
                            else None
                        )
                        routes.append(
                            JavaHttpRoute(
                                kind="CLIENT" if feign is not None else "SERVER",
                                registration=owner.symbol.id
                                + ":"
                                + symbol.id
                                + ":"
                                + str(index),
                                symbol=symbol,
                                path=path,
                                methods=methods,
                                consumes=method_mapping.consumes
                                or class_mapping.consumes,
                                produces=method_mapping.produces
                                or class_mapping.produces,
                                params=(*class_mapping.params, *method_mapping.params),
                                headers=(
                                    *class_mapping.headers,
                                    *method_mapping.headers,
                                ),
                                service=service,
                                parameters=parameters,
                                responses=responses,
                                evidence=(
                                    self.evidence(
                                        owner, owner.node, "spring.controller"
                                    ),
                                    *controller_proof,
                                    *class_mapping.evidence,
                                    *method_mapping.evidence,
                                    *client_proof,
                                    self.evidence(defining, node, "java.handler"),
                                ),
                                incomplete=tuple(dict.fromkeys(incomplete)),
                            )
                        )
        return tuple(
            sorted(routes, key=lambda r: (r.symbol.id, r.registration, r.path or ""))
        )


def java_http_catalog(
    pairs: tuple[tuple[SourceInput, JavaSymbolsResult], ...], profile: str
) -> JavaHttpCatalog:
    """Build immutable HTTP declarations without reparsing Java or loading a classpath."""
    collector = _Collector(pairs)
    provisional = JavaHttpCatalog(
        key=CATALOG_KEY,
        version=VERSION,
        source_files=tuple(
            s.file for s, _ in sorted(pairs, key=lambda p: p[0].file.path)
        ),
        routes=collector.collect(),
        issues=tuple(dict.fromkeys(collector.issues)),
        failed_paths=tuple(sorted(collector.failed)),
    )
    digest = hashlib.sha256(
        json.dumps(
            [profile, provisional.model_dump(mode="json")],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return provisional.model_copy(update={"version": VERSION + ":" + digest})
