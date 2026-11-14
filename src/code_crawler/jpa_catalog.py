"""Typed Jakarta/Javax annotation catalog; logical mappings, never guessed SQL."""

from collections import defaultdict
from dataclasses import dataclass

from sqlglot import Dialect, exp
from tree_sitter import Node

from code_crawler import java
from code_crawler.java_calls import JavaCallAnalyzer, _Class, _File, _modifiers
from code_crawler.java_semantic import JavaSemanticAnalyzer, _envelope
from code_crawler.java_sql import _SqlFlow
from code_crawler.ucm import EntityType, OrmMapping, OrmQuery, SqlIdentifier, Symbol

_JPA = {
    "Entity",
    "Table",
    "Column",
    "Id",
    "EmbeddedId",
    "Version",
    "Transient",
    "Access",
    "AccessType",
    "MappedSuperclass",
    "Embeddable",
    "Embedded",
    "Inheritance",
    "SecondaryTable",
    "SecondaryTables",
    "AttributeOverride",
    "AttributeOverrides",
    "ManyToOne",
    "OneToOne",
    "OneToMany",
    "ManyToMany",
    "ElementCollection",
    "JoinColumn",
    "JoinTable",
    "NamedQuery",
    "NamedQueries",
    "NamedNativeQuery",
    "NamedNativeQueries",
    "EntityManager",
    "Query",
    "TypedQuery",
}
_RELATIONSHIPS = {
    "ManyToOne",
    "OneToOne",
    "OneToMany",
    "ManyToMany",
    "ElementCollection",
}


def qualify_jpa(
    analyzer: JavaCallAnalyzer, name: str, file: _File, owner: _Class
) -> str | None:
    """Resolve known persistence namespace imports, refusing ambiguous wildcard packages."""
    result = JavaCallAnalyzer.qualify(analyzer, name, file, owner)
    if result is not None:
        return result
    root = file.result._extractor.parsed._tree.root_node
    packages = []
    for node in root.named_children:
        if node.type != "import_declaration" or any(
            c.type == "static" for c in node.children
        ):
            continue
        if any(c.type == "asterisk" for c in node.named_children):
            package = next(
                (
                    java._text(c)
                    for c in node.named_children
                    if c.type in ("identifier", "scoped_identifier")
                ),
                None,
            )
            if package:
                packages.append(package)
    if any(
        p not in ("jakarta.persistence", "javax.persistence", "java.util")
        for p in packages
    ):
        return None
    if name in _JPA:
        found = [
            p + "." + name
            for p in packages
            if p in ("jakarta.persistence", "javax.persistence")
        ]
        return found[0] if len(found) == 1 else None
    if (
        name
        in (
            "String",
            "Object",
            "Boolean",
            "Integer",
            "Long",
            "Double",
            "Float",
            "Short",
            "Byte",
            "Character",
        )
        and packages
    ):
        return "java.lang." + name
    return None


def annotations(
    analyzer: JavaCallAnalyzer, file: _File, owner: _Class, node: Node
) -> dict[str, Node]:
    modifiers = next((c for c in node.named_children if c.type == "modifiers"), None)
    result = {}
    if modifiers:
        for annotation in modifiers.named_children:
            if annotation.type not in ("annotation", "marker_annotation"):
                continue
            name = java._text(annotation.child_by_field_name("name"))
            resolved = qualify_jpa(analyzer, name, file, owner)
            if (
                resolved
                and resolved not in analyzer.classes
                and (
                    resolved.startswith(("jakarta.persistence.", "javax.persistence."))
                    and resolved.rsplit(".", 1)[-1]
                    not in ("Query", "TypedQuery", "EntityManager", "AccessType")
                    or resolved == "org.springframework.data.jpa.repository.Query"
                )
            ):
                result[resolved.rsplit(".", 1)[-1]] = annotation
    return result


def arguments(annotation: Node | None) -> dict[str, Node]:
    if annotation is None:
        return {}
    args = annotation.child_by_field_name("arguments")
    if args is None:
        return {}
    result = {}
    for child in args.named_children:
        if child.type == "element_value_pair":
            result[java._text(child.child_by_field_name("key"))] = (
                child.child_by_field_name("value")
            )
        elif child.type not in ("line_comment", "block_comment"):
            result["value"] = child
    return result


def literal_string(node: Node | None, constants: dict) -> str | None:
    if node is None:
        return None
    value = _SqlFlow(constants, java._span(node)).evaluate(node)
    return (
        value.text
        if value is not None and value.is_string and not value.partial
        else None
    )


def identifier(text: str | None, dialect: str) -> SqlIdentifier | None:
    if not text:
        return None
    quoted = len(text) >= 2 and (text[0], text[-1]) in (
        ('"', '"'),
        ("`", "`"),
        ("[", "]"),
    )
    value = text[1:-1].replace(text[-1] * 2, text[-1]) if quoted else text

    return SqlIdentifier(
        text=value,
        quoted=quoted,
        normalized=Dialect.get_or_raise(dialect)
        .normalize_identifier(exp.Identifier(this=value, quoted=quoted))
        .name,
    )


def _access(
    analyzer: JavaCallAnalyzer, file: _File, owner: _Class, annotation: Node | None
) -> str | None:
    value = arguments(annotation).get("value")
    if value is None or value.type != "field_access":
        return None
    descriptor = qualify_jpa(
        analyzer, java._text(value.child_by_field_name("object")), file, owner
    )
    mode = java._text(value.child_by_field_name("field"))
    return (
        mode
        if descriptor
        in ("jakarta.persistence.AccessType", "javax.persistence.AccessType")
        and mode in ("FIELD", "PROPERTY")
        else None
    )


@dataclass(frozen=True)
class QueryDefinition:
    query: OrmQuery
    file: _File
    value_node: Node | None
    value: java._Value | None


class JpaCatalog:
    def __init__(self, analyzer: JavaSemanticAnalyzer) -> None:
        self.analyzer = analyzer
        self.mappings: dict[str, OrmMapping] = {}
        self.by_file = defaultdict(list)
        self.entity_by_symbol = {}
        self.attributes = defaultdict(list)
        self.names = defaultdict(list)
        self.queries: dict[str, QueryDefinition] = {}
        self.named = defaultdict(list)
        self._build()

    def _build(self) -> None:
        analyzer = self.analyzer
        for owner in analyzer.class_keys.values():
            file = owner.file
            extractor = file.result._extractor
            constants = extractor.parsed._constant_scopes.get(
                owner.symbol.qualified_name, {}
            )
            anns = annotations(analyzer, file, owner, owner.node)
            role = next(
                (
                    name
                    for name in ("Entity", "MappedSuperclass", "Embeddable")
                    if name in anns
                ),
                None,
            )
            members = []
            for symbol in file.result.analysis.entities:
                if not isinstance(symbol, Symbol) or symbol.symbol_kind not in (
                    "FIELD",
                    "METHOD",
                ):
                    continue
                declaration = extractor.symbol_nodes[symbol.id]
                if symbol.symbol_kind == "FIELD":
                    field = declaration.parent
                    if (
                        field is None
                        or field.type not in java._FIELDS
                        or field.parent != owner.node.child_by_field_name("body")
                    ):
                        continue
                    node = field
                else:
                    method = analyzer.methods.get(symbol.id)
                    if method is None or method.owner.symbol.id != owner.symbol.id:
                        continue
                    node = declaration
                members.append((symbol, node, annotations(analyzer, file, owner, node)))
            if role:
                placements = {
                    ("FIELD" if symbol.symbol_kind == "FIELD" else "PROPERTY")
                    for symbol, _, member_anns in members
                    if "Id" in member_anns or "EmbeddedId" in member_anns
                }
                mode = _access(analyzer, file, owner, anns.get("Access")) or (
                    next(iter(placements)) if len(placements) == 1 else "UNKNOWN"
                )
                reasons = []
                if (
                    role == "Entity"
                    and mode in ("FIELD", "PROPERTY")
                    and mode not in placements
                ):
                    reasons.append(
                        "no identifier is declared in the selected access mode"
                    )
                if mode == "UNKNOWN":
                    reasons.append(
                        "default access cannot be proved without a unique Id placement or explicit Access"
                    )
                if owner.inherits or any(
                    name in anns
                    for name in (
                        "Inheritance",
                        "SecondaryTable",
                        "SecondaryTables",
                        "AttributeOverride",
                        "AttributeOverrides",
                    )
                ):
                    reasons.append(
                        "inheritance/secondary-table/override mappings are not expanded"
                    )
                entity_args = arguments(anns[role])
                table_args = arguments(anns.get("Table"))
                entity_name = (
                    literal_string(entity_args.get("name"), constants)
                    or owner.symbol.name
                )
                for key, node in (*entity_args.items(), *table_args.items()):
                    if (
                        key in ("name", "schema", "catalog")
                        and literal_string(node, constants) is None
                    ):
                        reasons.append(
                            "annotation identifier expression is not a known constant string"
                        )
                table_name = (
                    literal_string(table_args.get("name"), constants) or entity_name
                    if role == "Entity"
                    else None
                )
                mapping = OrmMapping(
                    **_envelope(
                        owner.symbol.repository_id,
                        EntityType.ORM_MAPPING,
                        "jpa.mapping:" + owner.symbol.logical_key,
                        entity_name,
                        extractor.range(owner.node),
                    ),
                    mapping_kind="ENTITY",
                    entity_role={
                        "Entity": "ENTITY",
                        "MappedSuperclass": "MAPPED_SUPERCLASS",
                        "Embeddable": "EMBEDDABLE",
                    }[role],
                    symbol_id=owner.symbol.id,
                    owner_symbol_id=owner.symbol.id,
                    entity_name=entity_name,
                    access_mode=mode,
                    catalog_name=identifier(
                        literal_string(table_args.get("catalog"), constants),
                        analyzer.dialect,
                    ),
                    schema_name=identifier(
                        literal_string(table_args.get("schema"), constants),
                        analyzer.dialect,
                    ),
                    table_name=identifier(table_name, analyzer.dialect),
                    status="PARTIAL" if reasons else "COMPLETE",
                    reasons=tuple(dict.fromkeys(reasons)),
                )
                self._add(mapping, file)
                self.entity_by_symbol[owner.symbol.id] = mapping
                if role == "Entity":
                    self.names[entity_name].append(mapping)
                for symbol, node, member_anns in members:
                    if "Transient" in member_anns or _modifiers(node) & {
                        "static",
                        "transient",
                    }:
                        continue
                    own_mode = "FIELD" if symbol.symbol_kind == "FIELD" else "PROPERTY"
                    explicit = _access(analyzer, file, owner, member_anns.get("Access"))
                    if own_mode != (explicit or mode) and not (
                        mode == "UNKNOWN"
                        and any(
                            a in member_anns
                            for a in ("Column", "Id", "EmbeddedId", "Version")
                        )
                    ):
                        continue
                    name = symbol.name
                    if own_mode == "PROPERTY":
                        if symbol.signature.parameter_types:
                            continue
                        prefix = (
                            "get"
                            if name.startswith("get")
                            else "is"
                            if name.startswith("is")
                            and symbol.signature.return_type
                            and symbol.signature.return_type.name
                            in ("boolean", "Boolean", "java.lang.Boolean")
                            else None
                        )
                        if prefix is None or len(name) <= len(prefix):
                            continue
                        name = name[len(prefix) :]
                        name = (
                            name
                            if len(name) > 1 and name[:2].isupper()
                            else name[0].lower() + name[1:]
                        )
                    attribute_reasons = []
                    if mode == "UNKNOWN":
                        attribute_reasons.append("entity access mode is unknown")
                    kind = (
                        "ID"
                        if "Id" in member_anns
                        else "VERSION"
                        if "Version" in member_anns
                        else "EMBEDDED"
                        if any(a in member_anns for a in ("Embedded", "EmbeddedId"))
                        else "RELATIONSHIP"
                        if _RELATIONSHIPS.intersection(member_anns)
                        else "BASIC"
                    )
                    if kind in ("EMBEDDED", "RELATIONSHIP"):
                        attribute_reasons.append(
                            "embedded/relationship/cascade/collection mapping is not flattened"
                        )
                    column_args = arguments(
                        member_anns.get("JoinColumn")
                        if kind == "RELATIONSHIP"
                        else member_anns.get("Column")
                    )
                    column = literal_string(column_args.get("name"), constants)
                    if "name" in column_args and column is None:
                        attribute_reasons.append(
                            "column name expression is not a known string"
                        )
                    if kind in ("BASIC", "ID", "VERSION") and not column:
                        column = name
                    flags = {}
                    for flag in ("nullable", "insertable", "updatable"):
                        expression = column_args.get(flag)
                        if expression is None:
                            flags[flag] = not (flag == "nullable" and kind == "ID")
                        elif java._text(expression) in ("true", "false"):
                            flags[flag] = java._text(expression) == "true"
                        else:
                            flags[flag] = None
                            attribute_reasons.append("column boolean flag is not known")
                    attribute = OrmMapping(
                        **_envelope(
                            symbol.repository_id,
                            EntityType.ORM_MAPPING,
                            "jpa.mapping:" + symbol.logical_key,
                            name,
                            extractor.range(node),
                        ),
                        mapping_kind="ATTRIBUTE",
                        entity_role=mapping.entity_role,
                        symbol_id=symbol.id,
                        owner_symbol_id=owner.symbol.id,
                        entity_name=entity_name,
                        attribute_name=name,
                        attribute_kind=kind,
                        access_mode=own_mode,
                        catalog_name=mapping.catalog_name,
                        schema_name=mapping.schema_name,
                        table_name=mapping.table_name,
                        column_name=identifier(column, analyzer.dialect),
                        status="PARTIAL" if attribute_reasons else "COMPLETE",
                        reasons=tuple(dict.fromkeys(attribute_reasons)),
                        **flags,
                    )
                    self._add(attribute, file)
                    self.attributes[mapping.id].append(attribute)
            for symbol, node, member_anns in [
                (owner.symbol, owner.node, anns),
                *members,
            ]:
                if symbol.symbol_kind not in ("CLASS", "METHOD", "CONSTRUCTOR"):
                    continue
                for name, annotation in member_anns.items():
                    if name in ("NamedQuery", "NamedNativeQuery", "Query"):
                        self._query(file, owner, symbol, annotation, name, constants)
                    elif name in ("NamedQueries", "NamedNativeQueries"):
                        pending = list(annotation.named_children)
                        while pending:
                            child = pending.pop()
                            if child.type == "annotation":
                                resolved = qualify_jpa(
                                    analyzer,
                                    java._text(child.child_by_field_name("name")),
                                    file,
                                    owner,
                                )
                                kind = (
                                    resolved.rsplit(".", 1)[-1]
                                    if resolved
                                    and resolved.startswith(
                                        ("javax.persistence.", "jakarta.persistence.")
                                    )
                                    else None
                                )
                                if kind in ("NamedQuery", "NamedNativeQuery"):
                                    self._query(
                                        file, owner, symbol, child, kind, constants
                                    )
                            pending.extend(child.named_children)

    def _add(self, mapping: OrmMapping, file: _File) -> None:
        self.mappings[mapping.id] = mapping
        self.by_file[file.source.file.path].append(mapping)

    def _query(
        self,
        file: _File,
        owner: _Class,
        symbol: Symbol,
        annotation: Node,
        name: str,
        constants: dict,
    ) -> None:
        args = arguments(annotation)
        native = (
            name == "NamedNativeQuery"
            or name == "Query"
            and java._text(args.get("nativeQuery")) == "true"
        )
        node = args.get("query") if name != "Query" else args.get("value")
        value = (
            _SqlFlow(constants, java._span(annotation)).evaluate(node)
            if node is not None
            else None
        )
        reasons = []
        unknown_native = (
            name == "Query"
            and "nativeQuery" in args
            and java._text(args["nativeQuery"]) not in ("true", "false")
        )
        if unknown_native:
            reasons.append(
                "nativeQuery flag is unknown; SQL/JPQL domain is not guessed"
            )
        if (
            value is None
            or not value.is_string
            or value.partial
            or not value.text.strip()
        ):
            reasons.append("query declaration text is not fully recovered")
        query_name = (
            literal_string(args.get("name"), constants) if name != "Query" else None
        )
        if name != "Query" and not query_name:
            reasons.append("named query name is not a known string")
        key = "jpa.query:" + symbol.logical_key + f":annotation:{annotation.start_byte}"
        query = OrmQuery(
            **_envelope(
                symbol.repository_id,
                EntityType.ORM_QUERY,
                key,
                query_name or "Repository query",
                file.result._extractor.range(annotation),
            ),
            owner_symbol_id=symbol.id,
            query_kind="UNKNOWN" if unknown_native else "NATIVE" if native else "JPQL",
            query_name=query_name,
            text=value.text.strip() if value and value.text.strip() else None,
            status="PARTIAL" if reasons else "COMPLETE",
            reasons=tuple(reasons),
        )
        definition = QueryDefinition(query, file, node, value)
        self.queries[query.id] = definition
        if query_name:
            self.named[query_name].append(definition)
