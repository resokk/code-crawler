"""Conservative, repository-local bindings over existing BPMN and Java facts."""

import re
from collections import defaultdict
from dataclasses import dataclass

from code_crawler.bpmn_adapter import BPMN, CAMUNDA, FLOW_NODES, ZEEBE
from code_crawler.bpmn_java_catalog import JavaBindingCatalog, JavaHandler
from code_crawler.incremental import FileAnalysis, SourceInput
from code_crawler.source_adapters import AdapterFileResult
from code_crawler.ucm import (
    Certainty,
    Coverage,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    Relation,
    RelationKind,
    Resolution,
    SourceDiagnostic,
    Symbol,
    SymbolSelector,
    Value,
    logical_id,
)

FLOWABLE = "http://flowable.org/bpmn"
BINDING_VERSION = "bpmn.java/1"
BINDING_PROFILES = ("auto", "camunda7", "camunda8", "flowable6", "flowable7")
_ENGINES = {CAMUNDA: "camunda7", ZEEBE: "camunda8", FLOWABLE: "flowable"}
_BEAN = re.compile(r"[$#]\{\s*([A-Za-z_$][\w$]*)\s*\}")
_VARIABLE = re.compile(r"(?:[$#]\{\s*([A-Za-z_$][\w$]*)\s*\}|=\s*([A-Za-z_$][\w$]*))")


def binding_coverage(profile: str) -> Coverage:
    return Coverage(
        capability="bpmn.java.bindings",
        analyzer_version=BINDING_VERSION,
        status="PARTIAL",
        reasons=(
            "Static profile "
            + profile
            + "; runtime registration and execution are not proved.",
            "Variable-name matches do not prove runtime data lineage.",
        ),
    )


def _supports(profile: str, engine: str) -> bool:
    return (
        profile == "auto"
        or profile == engine
        or engine == "flowable"
        and profile in ("flowable6", "flowable7")
    )


@dataclass(frozen=True)
class _Request:
    engine: str
    kind: str
    value: str
    origin: Symbol
    role: str


def bind_bpmn(
    source: SourceInput,
    schema: AdapterFileResult,
    catalog: JavaBindingCatalog | None,
    profile: str,
) -> AdapterFileResult:
    """Add typed handlers/mappings while retaining uncertainty and captured evidence."""
    coverage = binding_coverage(profile)
    if schema.capabilities[0].status == "UNSUPPORTED":
        return AdapterFileResult(
            analysis=schema.analysis,
            diagnostics=schema.diagnostics,
            capabilities=(
                *schema.capabilities,
                Coverage(
                    capability=coverage.capability,
                    analyzer_version=BINDING_VERSION,
                    status="UNSUPPORTED",
                    reasons=("Not a BPMN document.",),
                ),
            ),
        )
    entities = list(schema.analysis.entities)
    diagnostics = list(schema.diagnostics)
    by_id = {entity.id: entity for entity in entities}
    symbols = {key: value for key, value in by_id.items() if isinstance(value, Symbol)}
    attributes: dict[str, dict[str, str]] = defaultdict(dict)
    texts: dict[str, str] = {}
    parent: dict[str, str] = {}
    for entity in entities:
        if not isinstance(entity, Relation) or entity.resolution.target is None:
            continue
        target = by_id[entity.resolution.target.id]
        if entity.relation_kind == RelationKind.BPMN_ATTRIBUTE:
            attributes[entity.source.id][target.name] = target.literal
        elif entity.relation_kind == RelationKind.BPMN_TEXT:
            texts[entity.source.id] = target.literal
        elif entity.relation_kind == RelationKind.CONTAINS and isinstance(
            target, Symbol
        ):
            parent[target.id] = entity.source.id

    def owner(symbol: Symbol) -> Symbol | None:
        key = parent.get(symbol.id)
        while key is not None:
            ancestor = symbols[key]
            if ancestor.qualified_name in {f"{{{BPMN}}}{name}" for name in FLOW_NODES}:
                return ancestor
            key = parent.get(key)
        return None

    def ref(entity: Symbol | Value) -> EntityRef:
        return EntityRef(id=entity.id, entity_type=entity.entity_type)

    def base(kind: EntityType, key: str, name: str, symbol: Symbol) -> dict:
        logical_key = symbol.logical_key + ":" + BINDING_VERSION + ":" + key
        return {
            "repository_id": source.file.repository_id,
            "logical_key": logical_key,
            "id": logical_id(source.file.repository_id, kind, logical_key),
            "name": name,
            "source_range": symbol.source_range,
        }

    def evidence(symbol: Symbol, rule: str) -> Evidence:
        return Evidence(
            source_range=symbol.source_range,
            analyzer="bpmn.java",
            analyzer_version=BINDING_VERSION,
            rule=rule,
            description="Explicit BPMN configuration; no runtime execution asserted.",
        )

    def diagnostic(symbol: Symbol, code: str, message: str) -> None:
        diagnostics.append(
            SourceDiagnostic(
                severity="WARNING",
                code="bpmn.java." + code,
                message=message,
                source_range=symbol.source_range,
            )
        )

    def relation(
        kind: RelationKind,
        origin: Symbol,
        resolution: Resolution,
        key: str,
        proof: tuple[Evidence, ...],
        certainty: Certainty = Certainty.INFERRED,
    ) -> None:
        entities.append(
            Relation(
                **base(EntityType.RELATION, key, kind.value, origin),
                relation_kind=kind,
                source=ref(origin),
                resolution=resolution,
                evidence=tuple(dict.fromkeys(proof)),
                certainty=certainty,
                coverage=coverage,
            )
        )

    requests: dict[str, list[_Request]] = defaultdict(list)
    for symbol in symbols.values():
        attrs = attributes[symbol.id]
        if symbol.qualified_name == f"{{{BPMN}}}serviceTask":
            for namespace, engine in ((CAMUNDA, "camunda7"), (FLOWABLE, "flowable")):
                for name, kind, role in (
                    ("class", "CLASS", "class"),
                    ("delegateExpression", "BEAN", "delegateExpression"),
                    ("expression", "EXPRESSION", "expression"),
                    ("topic", "WORKER", "worker"),
                ):
                    if value := attrs.get(f"{{{namespace}}}{name}"):
                        requests[symbol.id].append(
                            _Request(engine, kind, value, symbol, role)
                        )
        if symbol.qualified_name == f"{{{ZEEBE}}}taskDefinition" and (
            value := attrs.get("type")
        ):
            task = owner(symbol)
            if task is not None and task.qualified_name == f"{{{BPMN}}}serviceTask":
                requests[task.id].append(
                    _Request("camunda8", "WORKER", value, symbol, "worker")
                )

    selected: dict[str, tuple[JavaHandler, ...]] = {}
    remove_externals = set()
    for task_id, configured in requests.items():
        task = symbols[task_id]
        candidates: list[JavaHandler] = []
        unresolved: list[_Request] = []
        proof = []
        for request in configured:
            remove_externals.add((request.origin.id, request.role))
            proof.append(evidence(request.origin, request.engine + "." + request.kind))
            selector = request.value
            if not _supports(profile, request.engine):
                diagnostic(
                    task,
                    "UNSUPPORTED_PROFILE",
                    "Binding namespace is outside selected profile " + profile,
                )
                unresolved.append(request)
                continue
            if request.kind == "BEAN":
                match = _BEAN.fullmatch(selector)
                selector = match[1] if match else None
            elif request.kind == "EXPRESSION" or any(
                token in selector for token in ("${", "#{", "=")
            ):
                selector = None
            if selector is None:
                diagnostic(
                    task,
                    "DYNAMIC_SELECTOR",
                    "Expression is preserved without evaluation: " + request.value,
                )
            matches = (
                tuple(
                    handler
                    for handler in catalog.handlers
                    if handler.engine == request.engine
                    and handler.kind == request.kind
                    and handler.selector == selector
                )
                if catalog is not None and selector is not None
                else ()
            )
            if matches:
                candidates.extend(matches)
                proof.extend(item for handler in matches for item in handler.evidence)
            else:
                unresolved.append(request)
        grouped = {handler.symbol.id: handler for handler in candidates}
        refs = tuple(ref(grouped[key].symbol) for key in sorted(grouped))
        conflict = len(configured) > 1
        if len(refs) > 1:
            resolution = Resolution(
                status="AMBIGUOUS",
                candidates=refs,
                reason="Multiple compatible local handlers; runtime selection is unknown.",
            )
        elif (
            refs
            and not conflict
            and len({h.registration for h in candidates}) == 1
            and not (catalog and catalog.failed_paths)
        ):
            resolution = Resolution(status="RESOLVED", target=refs[0])
        elif refs:
            resolution = Resolution(
                status="PARTIAL",
                candidates=refs,
                reason="Conflicting configuration, duplicate registrations or incomplete Java catalog.",
            )
        else:
            resolution = Resolution(
                status="UNRESOLVED",
                reason="No supported compatible local Java handler.",
            )
        if conflict:
            diagnostic(
                task,
                "CONFLICTING_BINDINGS",
                "Multiple binding selectors on one service task.",
            )
        if catalog is not None and catalog.failed_paths:
            diagnostic(
                task,
                "PARTIAL_JAVA_CATALOG",
                "Java parser diagnostics excluded files from binding candidates.",
            )
        relation(
            RelationKind.BPMN_HANDLER,
            task,
            resolution,
            "handler",
            tuple(proof),
            Certainty.INFERRED if refs else Certainty.UNKNOWN,
        )
        selected[task_id] = tuple(grouped[key] for key in sorted(grouped))
        for index, request in enumerate(unresolved):
            entities.append(
                ExternalReference(
                    **base(
                        EntityType.EXTERNAL_REFERENCE,
                        f"external:{index}:{request.engine}:{request.role}",
                        request.role,
                        task,
                    ),
                    source=ref(task),
                    selector=SymbolSelector(
                        qualified_name=f"bpmn.{request.role}::{request.value}"
                    ),
                    reason="Deferred engine selector; no other repository or runtime container consulted.",
                    evidence=(
                        evidence(
                            request.origin, request.engine + ".external." + request.role
                        ),
                    ),
                    certainty=Certainty.UNKNOWN,
                    coverage=coverage,
                )
            )

    # Schema selectors are replaced by contextual results, retaining process selectors unchanged.
    entities = [
        entity
        for entity in entities
        if not (
            isinstance(entity, ExternalReference)
            and entity.coverage.capability == "bpmn.schema"
            and (entity.source.id, entity.name) in remove_externals
        )
    ]
    accesses: dict[str, list[tuple[str, str | None, Value, Evidence]]] = defaultdict(
        list
    )
    for task_id, handlers in selected.items():
        task = symbols[task_id]
        for handler in handlers:
            for index, access in enumerate(handler.variables):
                value = Value(
                    **base(
                        EntityType.VALUE,
                        f"variable:{handler.symbol.id}:{index}:{access.direction}",
                        access.name or "dynamic process variable",
                        task,
                    ),
                    value_kind="LITERAL" if access.name else "UNKNOWN",
                    literal=access.name,
                    partial=access.name is None,
                )
                entities.append(value)
                kind = (
                    RelationKind.BPMN_READS_VARIABLE
                    if access.direction == "READ"
                    else RelationKind.BPMN_WRITES_VARIABLE
                )
                # Facts are owned by the BPMN file; their evidence also points to the Java access.
                entities.append(
                    Relation(
                        **base(
                            EntityType.RELATION, f"access:{value.id}", kind.value, task
                        ),
                        relation_kind=kind,
                        source=ref(handler.symbol),
                        resolution=Resolution(status="RESOLVED", target=ref(value)),
                        evidence=(
                            evidence(task, "task.variable.context"),
                            access.evidence,
                        ),
                        certainty=Certainty.INFERRED,
                        coverage=coverage,
                    )
                )
                accesses[task_id].append(
                    (access.direction, access.name, value, access.evidence)
                )
                if access.name is None:
                    diagnostic(
                        task,
                        "DYNAMIC_VARIABLE",
                        "Java process variable name is not a supported literal.",
                    )

    for symbol in symbols.values():
        qname = symbol.qualified_name
        namespace, _, local = (
            qname[1:].partition("}") if qname.startswith("{") else ("", "", qname)
        )
        engine = _ENGINES.get(namespace)
        if engine is None or not _supports(profile, engine):
            continue
        direction = None
        variable = None
        attrs = attributes[symbol.id]
        parent_tag = (
            symbols[parent[symbol.id]].qualified_name if symbol.id in parent else None
        )
        if (
            namespace == CAMUNDA
            and local in ("inputParameter", "outputParameter")
            and parent_tag == f"{{{namespace}}}inputOutput"
        ):
            direction = "READ" if local == "inputParameter" else "WRITE"
            match = _VARIABLE.fullmatch(texts.get(symbol.id, "").strip())
            variable = (
                attrs.get("name")
                if direction == "READ"
                else (next((s for s in match.groups() if s), None) if match else None)
            )
        elif (
            namespace == ZEEBE
            and local in ("input", "output")
            and parent_tag == f"{{{ZEEBE}}}ioMapping"
        ):
            direction = "READ" if local == "input" else "WRITE"
            match = _VARIABLE.fullmatch(attrs.get("source", "").strip())
            variable = (
                attrs.get("target")
                if direction == "READ"
                else (next((s for s in match.groups() if s), None) if match else None)
            )
        elif namespace in (CAMUNDA, FLOWABLE) and local in ("in", "out"):
            direction = "READ" if local == "in" else "WRITE"
            variable = attrs.get("target" if direction == "READ" else "source")
        if direction is None:
            continue
        task = owner(symbol)
        if task is None:
            continue
        kind = (
            RelationKind.BPMN_INPUT_MAPPING
            if direction == "READ"
            else RelationKind.BPMN_OUTPUT_MAPPING
        )
        relation(
            kind,
            task,
            Resolution(status="RESOLVED", target=ref(symbol)),
            "mapping:" + symbol.id,
            (evidence(symbol, engine + ".variable.mapping"),),
            Certainty.STATIC_PROVEN,
        )
        matches = [
            (value, java_evidence)
            for access_direction, name, value, java_evidence in accesses[task.id]
            if access_direction == direction and name is not None and name == variable
        ]
        if matches:
            relation(
                RelationKind.BPMN_VARIABLE_BINDING,
                symbol,
                Resolution(
                    status="AMBIGUOUS" if len(matches) > 1 else "PARTIAL",
                    candidates=tuple(ref(value) for value, _ in matches),
                    reason="Variable name match only; runtime scopes, conversions and data flow are not proved.",
                ),
                "variable-binding",
                (
                    evidence(symbol, "mapping.name.candidate"),
                    *(item for _, item in matches),
                ),
            )
    dependencies = (
        tuple(
            sorted(
                {
                    *schema.analysis.dependencies,
                    *(
                        f.path
                        for f in catalog.source_files
                        if f.path != source.file.path
                    ),
                }
            )
        )
        if requests and catalog
        else schema.analysis.dependencies
    )
    return AdapterFileResult(
        analysis=FileAnalysis(
            path=source.file.path, entities=tuple(entities), dependencies=dependencies
        ),
        diagnostics=tuple(diagnostics),
        capabilities=(*schema.capabilities, coverage),
    )
