"""Restricted JPQL entity/property interpretation, distinct from physical SQL."""

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from code_crawler import sql
from code_crawler.jpa_catalog import JpaCatalog
from code_crawler.ucm import OrmMapping


@dataclass(frozen=True)
class JpaReference:
    kind: str
    name: str
    candidates: tuple[OrmMapping, ...]
    reason: str | None = None


@dataclass(frozen=True)
class JpqlAnalysis:
    status: str
    reasons: tuple[str, ...]
    references: tuple[JpaReference, ...]


def analyze_jpql(text: str, catalog: JpaCatalog) -> JpqlAnalysis:
    """Interpret a bounded JPQL subset against entity names and mapped properties."""
    try:
        parsed = [
            root for root in sqlglot.parse(text, read="postgres") if root is not None
        ]
    except (SqlglotError, RecursionError) as error:
        return JpqlAnalysis("UNSUPPORTED", (str(error),), ())
    if len(parsed) != 1 or not isinstance(
        parsed[0], (exp.Select, exp.Update, exp.Delete)
    ):
        return JpqlAnalysis(
            "UNSUPPORTED", ("JPQL profile supports one SELECT/UPDATE/DELETE",), ()
        )
    root = parsed[0]
    if any(root.find_all(exp.With, exp.CTE, exp.SetOperation)):
        return JpqlAnalysis(
            "UNSUPPORTED",
            ("CTE/set-operation HQL/vendor syntax is outside this JPQL profile",),
            (),
        )
    references = []
    reasons = []
    environments = {}
    for table in root.find_all(exp.Table):
        owner = table.find_ancestor(exp.Select, exp.Update, exp.Delete)
        name = ".".join(part.name for part in table.parts)
        found = tuple(catalog.names.get(name, ()))
        alias = table.alias_or_name
        environments.setdefault(id(owner), {})[alias.lower()] = found
        if len(found) > 1:
            reasons.append("ambiguous entity name across the repository: " + name)
        if not found:
            reasons.append(
                "unknown entity or unsupported relationship-join path: " + name
            )
        references.append(
            JpaReference(
                "ENTITY",
                name,
                found,
                None
                if found
                else "entity name/class is absent from the repository ORM catalog",
            )
        )
    for column in root.find_all(exp.Column):
        owner = column.find_ancestor(exp.Select, exp.Update, exp.Delete)
        sources = environments.get(id(owner), {})
        if not column.table and column.name.lower() in sources:
            continue
        selected = (
            sources.get(column.table.lower())
            if column.table
            else next(iter(sources.values()))
            if len(sources) == 1
            else None
        )
        if selected is None and column.table:
            parent = (
                owner.find_ancestor(exp.Select, exp.Update, exp.Delete)
                if owner
                else None
            )
            while parent is not None and selected is None:
                selected = environments.get(id(parent), {}).get(column.table.lower())
                parent = parent.find_ancestor(exp.Select, exp.Update, exp.Delete)
        attributes = tuple(
            attribute
            for mapping in selected or ()
            for attribute in catalog.attributes[mapping.id]
            if attribute.attribute_name == column.name
        )
        kind = "WRITE" if sql._is_assignment_target(column) else "READ"
        reason = (
            None
            if attributes
            else "property path/alias is unknown or requires unsupported relationship/derived-output mapping"
        )
        if column.db or column.catalog:
            attributes = ()
            reason = "multi-hop property navigation is not expanded"
            reasons.append(reason)
        if reason:
            reasons.append(reason)
        references.append(JpaReference(kind, column.sql(), attributes, reason))
    if root.args.get("joins"):
        reasons.append(
            "join/fetch/relationship cardinality and cascades are not expanded"
        )
    return JpqlAnalysis(
        "PARTIAL" if reasons else "COMPLETE",
        tuple(dict.fromkeys(reasons)),
        tuple(references),
    )
