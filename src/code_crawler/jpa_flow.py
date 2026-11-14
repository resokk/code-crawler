"""Local EntityManager/query invocation and query-handle snapshots."""

from dataclasses import dataclass

from tree_sitter import Node

from code_crawler import java
from code_crawler.java_bindings import BindingFlow, CapturedValue
from code_crawler.java_calls import _File, _Site
from code_crawler.java_database import JavaDatabaseAnalyzer

_EM = {"jakarta.persistence.EntityManager", "javax.persistence.EntityManager"}
_QUERY = {
    "jakarta.persistence.Query",
    "javax.persistence.Query",
    "jakarta.persistence.TypedQuery",
    "javax.persistence.TypedQuery",
}


@dataclass(frozen=True)
class QueryHandle:
    site: _Site
    kind: str
    value: java._Value | None
    value_node: Node | None
    connection_symbol_id: str | None


@dataclass(frozen=True)
class OrmCall:
    site: _Site
    kind: str
    connection_symbol_id: str | None
    query: QueryHandle | None
    entity_type: str | None
    values: tuple[CapturedValue, ...]
    reasons: tuple[str, ...]


class JpaFlow(BindingFlow):
    def __init__(
        self,
        analyzer: JavaDatabaseAnalyzer,
        file: _File,
        node: Node,
        constants: dict,
        queries: list[QueryHandle],
        calls: list[OrmCall],
    ) -> None:
        super().__init__(analyzer, file, node, constants, [])
        self.orm_queries = queries
        self.orm_calls = calls
        self.orm_handles: dict[str, QueryHandle] = {}
        self.orm_created: dict[int, QueryHandle] = {}

    def clone(self) -> "JpaFlow":
        result = super().clone()
        result.orm_handles = dict(self.orm_handles)
        result.orm_created = dict(self.orm_created)
        return result

    def query_handle(self, node: Node | None) -> QueryHandle | None:
        if node is None:
            return None
        if node.type == "parenthesized_expression":
            return self.query_handle(node.named_children[0])
        if node.type == "method_invocation":
            if node.id in self.orm_created:
                return self.orm_created[node.id]
            if java._text(node.child_by_field_name("name")) in (
                "setParameter",
                "setMaxResults",
                "setFirstResult",
                "setHint",
                "setFlushMode",
                "setLockMode",
            ):
                return self.query_handle(node.child_by_field_name("object"))
            return None
        return self.orm_handles.get(self.binding(node))

    def _declare(self, declarator: Node, depth: int) -> None:
        super()._declare(declarator, depth)
        key = self.binding(declarator.child_by_field_name("name"))
        handle = self.query_handle(declarator.child_by_field_name("value"))
        if key and handle:
            self.orm_handles[key] = handle

    def _assign(self, node: Node, depth: int) -> bool:
        result = super()._assign(node, depth)
        key = self.binding(node.child_by_field_name("left"))
        if key:
            self.orm_handles.pop(key, None)
            handle = self.query_handle(node.child_by_field_name("right"))
            if handle and java._text(node.child_by_field_name("operator")) == "=":
                self.orm_handles[key] = handle
        return result

    def escape(self, node: Node | None) -> None:
        pending = [node] if node is not None else []
        while pending:
            current = pending.pop()
            handle = self.query_handle(current)
            if handle:
                self.orm_handles = {
                    key: h
                    for key, h in self.orm_handles.items()
                    if h.site.node.id != handle.site.node.id
                }
                self.orm_created = {
                    key: h
                    for key, h in self.orm_created.items()
                    if h.site.node.id != handle.site.node.id
                }
            pending.extend(current.named_children)
        super().escape(node)

    def _invocation(self, node: Node, depth: int) -> None:
        if node.id in self.visited:
            return
        receiver = node.child_by_field_name("object")
        if (
            receiver is not None
            and receiver.type == "method_invocation"
            and self.preview(node) is None
        ):
            self._visit(receiver, depth)
        name_node = node.child_by_field_name("name")
        site = self.analyzer.sites.get(
            (self.file.source.file.path, name_node.start_byte)
        )
        if site is None:
            return super()._invocation(node, depth)
        name = java._text(name_node)
        arguments = node.child_by_field_name("arguments")
        args = tuple(arguments.named_children) if arguments else ()
        descriptor, is_class = self.analyzer.receiver(site)
        handle = self.query_handle(receiver)
        connection = (
            self.analyzer.data_symbol(receiver, site) if receiver is not None else None
        )
        connection_id = connection.id if connection else None
        trusted = not is_class and descriptor not in self.analyzer.classes
        if trusted and descriptor in _EM:
            if (
                name in ("createQuery", "createNativeQuery", "createNamedQuery")
                and args
            ):
                string = self.is_string(args[0], site)
                kind = (
                    "NATIVE"
                    if name == "createNativeQuery"
                    else "NAMED_REFERENCE"
                    if name == "createNamedQuery"
                    else "JPQL"
                    if string
                    else "CRITERIA"
                )
                value = self.preview(args[0]) if string else None
                handle = QueryHandle(site, kind, value, args[0], connection_id)
                self.orm_created[node.id] = handle
                self.orm_queries.append(handle)
                if name in ("createQuery", "createNamedQuery") and string:
                    self.evaluate(args[0])
            kind = {
                "persist": "PERSIST",
                "merge": "MERGE",
                "remove": "REMOVE",
                "find": "FIND",
                "getReference": "GET_REFERENCE",
                "refresh": "REFRESH",
                "flush": "FLUSH",
            }.get(name)
            if kind and (
                (name == "flush" and not args)
                or (name in ("persist", "merge", "remove") and len(args) == 1)
                or (name in ("find", "getReference") and len(args) in (2, 3, 4))
                or (name == "refresh" and len(args) in (1, 2, 3))
            ):
                type_name = None
                if args:
                    if (
                        name in ("find", "getReference")
                        and args[0].type == "class_literal"
                    ):
                        type_node = args[0].named_children[0]
                        type_name = self.analyzer.qualify(
                            java._text(type_node), self.file, site.caller.owner
                        )
                    elif name not in ("find", "getReference"):
                        type_name = self.analyzer.argument_type(args[0], site)
                self.orm_calls.append(
                    OrmCall(
                        site,
                        kind,
                        connection_id,
                        None,
                        type_name,
                        tuple(self.capture(arg) for arg in args),
                        self.path_reasons,
                    )
                )
        if (
            name
            in (
                "getResultList",
                "getSingleResult",
                "getSingleResultOrNull",
                "getResultStream",
                "executeUpdate",
            )
            and not args
            and trusted
            and (descriptor in _QUERY or descriptor is None and handle is not None)
        ):
            self.orm_calls.append(
                OrmCall(
                    site,
                    "QUERY_WRITE" if name == "executeUpdate" else "QUERY_READ",
                    handle.connection_symbol_id if handle else None,
                    handle,
                    None,
                    (),
                    self.path_reasons,
                )
            )
        super()._invocation(node, depth)
