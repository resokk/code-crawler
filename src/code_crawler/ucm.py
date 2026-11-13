"""Versioned UCM entity envelope and source location contract."""

import hashlib
import json
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
EntityId = Annotated[str, Field(pattern=r"^ucm:[0-9a-f]{64}$")]


class EntityType(StrEnum):
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"
    RELATION = "RELATION"
    OPERATION = "OPERATION"
    VALUE = "VALUE"
    SYMBOL = "SYMBOL"
    SCOPE = "SCOPE"
    OCCURRENCE = "OCCURRENCE"
    SOURCE_FILE = "SOURCE_FILE"
    CLASS = "CLASS"
    METHOD = "METHOD"
    SQL_CANDIDATE = "SQL_CANDIDATE"


def logical_id(repository_id: str, entity_type: EntityType, logical_key: str) -> str:
    """Compute a stable, repository-scoped identity independent of snapshots."""
    if not repository_id.strip() or not logical_key.strip():
        raise ValueError("repository_id and logical_key must be nonblank")
    payload = json.dumps(
        ["ucm", 1, repository_id, EntityType(entity_type).value, logical_key],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "ucm:" + hashlib.sha256(payload).hexdigest()


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Position(ContractModel):
    line: int = Field(ge=1)
    byte_column: int = Field(ge=0)


class SourceRange(ContractModel):
    source_file_id: EntityId
    start: Position
    end: Position

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if (self.end.line, self.end.byte_column) < (
            self.start.line,
            self.start.byte_column,
        ):
            raise ValueError("source range end precedes start")
        return self


class EntityEnvelope(ContractModel):
    contract_version: Literal[1] = 1
    repository_id: Text
    logical_key: Text
    entity_type: EntityType
    id: EntityId
    name: Text
    source_range: SourceRange | None = None

    @model_validator(mode="after")
    def valid_identity(self) -> Self:
        if self.id != logical_id(
            self.repository_id, self.entity_type, self.logical_key
        ):
            raise ValueError("id does not match logical identity")
        return self


class SourceFile(EntityEnvelope):
    entity_type: Literal[EntityType.SOURCE_FILE] = EntityType.SOURCE_FILE
    path: Text
    language: Text
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source_range: None = None

    @model_validator(mode="after")
    def valid_path(self) -> Self:
        if any(part in ("", ".", "..") for part in self.path.split("/")) or any(
            char in self.path for char in ("\\", "\0", ":")
        ):
            raise ValueError("path must be a canonical repository-relative POSIX path")
        if self.logical_key != self.path:
            raise ValueError("source file logical_key must equal path")
        return self


class CodeEntity(EntityEnvelope):
    entity_type: Literal[EntityType.CLASS, EntityType.METHOD, EntityType.SQL_CANDIDATE]


class Resolvable(ContractModel):
    resolution: Literal["UNRESOLVED", "RESOLVED", "AMBIGUOUS"] = "UNRESOLVED"
    target_symbol_id: EntityId | None = None

    @model_validator(mode="after")
    def consistent_target(self) -> Self:
        if (self.resolution == "RESOLVED") != (self.target_symbol_id is not None):
            raise ValueError("only RESOLVED references require a target")
        return self


class TypeRef(Resolvable):
    name: Text


class CallableSignature(ContractModel):
    parameter_types: tuple[TypeRef, ...] = ()
    return_type: TypeRef | None = None


def callable_key(owner_key: str, name: str, signature: CallableSignature) -> str:
    """Build overload identity from owner, name and ordered parameter types."""
    if not owner_key.strip() or not name.strip():
        raise ValueError("owner and callable name must be nonblank")
    return json.dumps(
        ["callable", owner_key, name, [t.name for t in signature.parameter_types]],
        ensure_ascii=False,
        separators=(",", ":"),
    )


class Symbol(EntityEnvelope):
    entity_type: Literal[EntityType.SYMBOL] = EntityType.SYMBOL
    symbol_kind: Literal[
        "CLASS", "METHOD", "CONSTRUCTOR", "FIELD", "PARAMETER", "LOCAL_VARIABLE"
    ]
    qualified_name: Text
    scope_id: EntityId | None = None
    type_ref: TypeRef | None = None
    owner_key: Text | None = None
    signature: CallableSignature | None = None

    @model_validator(mode="after")
    def valid_signature(self) -> Self:
        if self.symbol_kind in ("METHOD", "CONSTRUCTOR"):
            if self.signature is None or self.owner_key is None:
                raise ValueError("callable requires signature and owner_key")
            if self.logical_key != callable_key(
                self.owner_key, self.name, self.signature
            ):
                raise ValueError("callable logical_key does not match signature")
        elif self.signature is not None or self.owner_key is not None:
            raise ValueError("non-callable cannot have signature or owner_key")
        return self


class Scope(EntityEnvelope):
    entity_type: Literal[EntityType.SCOPE] = EntityType.SCOPE
    scope_kind: Literal["FILE", "TYPE", "CALLABLE", "BLOCK"]
    parent_scope_id: EntityId | None = None
    owner_symbol_id: EntityId | None = None


class Occurrence(EntityEnvelope, Resolvable):
    entity_type: Literal[EntityType.OCCURRENCE] = EntityType.OCCURRENCE
    occurrence_kind: Literal["DECLARATION", "REFERENCE", "READ", "WRITE", "CALL"]
    source_range: SourceRange
    scope_id: EntityId


class Value(EntityEnvelope):
    entity_type: Literal[EntityType.VALUE] = EntityType.VALUE
    value_kind: Literal["LITERAL", "SYMBOLIC", "UNKNOWN"]
    type_ref: TypeRef | None = None
    partial: bool = False
    literal: str | int | Annotated[float, Field(allow_inf_nan=False)] | bool | None = (
        None
    )

    @model_validator(mode="after")
    def valid_value(self) -> Self:
        if self.value_kind == "LITERAL":
            if self.partial:
                raise ValueError("literal cannot be partial")
        elif self.literal is not None:
            raise ValueError("only LITERAL can carry a literal payload")
        if self.value_kind == "UNKNOWN" and not self.partial:
            raise ValueError("unknown value must be partial")
        return self


class Operation(EntityEnvelope):
    entity_type: Literal[EntityType.OPERATION] = EntityType.OPERATION
    operation_kind: Literal["READ", "ASSIGN", "CALL", "RETURN", "CONCAT"]
    scope_id: EntityId
    input_value_ids: tuple[EntityId, ...] = ()
    output_value_ids: tuple[EntityId, ...] = ()
    callee: TypeRef | None = None

    @model_validator(mode="after")
    def valid_flow(self) -> Self:
        inputs, outputs = len(self.input_value_ids), len(self.output_value_ids)
        if len(set(self.output_value_ids)) != outputs:
            raise ValueError("operation outputs must be unique")
        if set(self.input_value_ids) & set(self.output_value_ids):
            raise ValueError("input and output definitions must be distinct")
        valid = {
            "READ": inputs == 0 and outputs == 1,
            "ASSIGN": inputs == 1 and outputs == 1,
            "CONCAT": inputs >= 2 and outputs == 1,
            "RETURN": inputs <= 1 and outputs == 0,
            "CALL": outputs <= 1,
        }
        if not valid[self.operation_kind]:
            raise ValueError("invalid operand cardinality for operation")
        if self.callee is not None and self.operation_kind != "CALL":
            raise ValueError("only CALL may have a callee")
        return self


class EntityRef(ContractModel):
    id: EntityId
    entity_type: EntityType


class Resolution(ContractModel):
    status: Literal["RESOLVED", "UNRESOLVED", "AMBIGUOUS", "PARTIAL"]
    target: EntityRef | None = None
    candidates: tuple[EntityRef, ...] = ()
    reason: Text | None = None

    @model_validator(mode="after")
    def valid_resolution(self) -> Self:
        if len({candidate.id for candidate in self.candidates}) != len(self.candidates):
            raise ValueError("resolution candidates must be unique")
        if self.status == "RESOLVED":
            if self.target is None or self.candidates:
                raise ValueError("RESOLVED requires target and no candidates")
        else:
            if self.target is not None or self.reason is None:
                raise ValueError("unresolved statuses require reason and no target")
            minimum = {"UNRESOLVED": 0, "PARTIAL": 1, "AMBIGUOUS": 2}[self.status]
            if len(self.candidates) < minimum:
                raise ValueError("insufficient resolution candidates")
            if self.status == "UNRESOLVED" and self.candidates:
                raise ValueError("UNRESOLVED cannot carry candidates")
        return self


class Certainty(StrEnum):
    STATIC_PROVEN = "STATIC_PROVEN"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class Coverage(ContractModel):
    capability: Text
    analyzer_version: Text
    status: Literal["COMPLETE", "PARTIAL", "UNSUPPORTED"]
    reasons: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def valid_coverage(self) -> Self:
        if (self.status == "COMPLETE") == bool(self.reasons):
            raise ValueError("only incomplete coverage requires reasons")
        return self


class Evidence(ContractModel):
    source_range: SourceRange
    analyzer: Text
    analyzer_version: Text
    rule: Text
    description: Text


class RelationKind(StrEnum):
    EXTERNAL_DEPENDENCY = "EXTERNAL_DEPENDENCY"
    CONTAINS = "CONTAINS"
    DECLARES = "DECLARES"
    REFERENCES = "REFERENCES"
    CALLS = "CALLS"
    CONSUMES = "CONSUMES"
    PRODUCES = "PRODUCES"
    FLOWS_TO = "FLOWS_TO"


def _pairs(sources: str, targets: str) -> frozenset[tuple[EntityType, EntityType]]:
    return frozenset(
        (EntityType(s), EntityType(t)) for s in sources.split() for t in targets.split()
    )


_RELATION_ENDPOINTS = MappingProxyType(
    {
        RelationKind.EXTERNAL_DEPENDENCY: _pairs(
            "SYMBOL METHOD OCCURRENCE OPERATION VALUE", "EXTERNAL_REFERENCE"
        ),
        RelationKind.CONTAINS: _pairs(
            "SOURCE_FILE CLASS SYMBOL SCOPE", "CLASS METHOD SYMBOL SCOPE OPERATION"
        ),
        RelationKind.DECLARES: _pairs("OCCURRENCE", "CLASS METHOD SYMBOL"),
        RelationKind.REFERENCES: _pairs("OCCURRENCE", "CLASS METHOD SYMBOL"),
        RelationKind.CALLS: _pairs("METHOD SYMBOL OPERATION", "METHOD SYMBOL"),
        RelationKind.CONSUMES: _pairs("OPERATION", "VALUE"),
        RelationKind.PRODUCES: _pairs("OPERATION", "VALUE"),
        RelationKind.FLOWS_TO: _pairs("VALUE", "VALUE"),
    }
)


def relation_registry() -> Mapping[
    RelationKind, frozenset[tuple[EntityType, EntityType]]
]:
    """Return the immutable normative registry of relation endpoint types."""
    return _RELATION_ENDPOINTS


class Relation(EntityEnvelope):
    entity_type: Literal[EntityType.RELATION] = EntityType.RELATION
    relation_kind: RelationKind
    source: EntityRef
    resolution: Resolution
    certainty: Certainty
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    coverage: Coverage

    @model_validator(mode="after")
    def valid_relation(self) -> Self:
        pairs = _RELATION_ENDPOINTS[self.relation_kind]
        if not any(source == self.source.entity_type for source, _ in pairs):
            raise ValueError("invalid relation source type")
        targets = self.resolution.candidates
        if self.resolution.target is not None:
            targets = (self.resolution.target,)
        for target in targets:
            if (self.source.entity_type, target.entity_type) not in pairs:
                raise ValueError("invalid relation endpoint pair")
        if (
            self.certainty == Certainty.STATIC_PROVEN
            and self.resolution.status != "RESOLVED"
        ):
            raise ValueError("STATIC_PROVEN requires resolved endpoints")
        if self.coverage.status == "UNSUPPORTED" and (
            self.resolution.status != "UNRESOLVED"
            or self.certainty != Certainty.UNKNOWN
        ):
            raise ValueError("unsupported capability cannot assert a relation")
        return self


def validate_relation_endpoints(
    relation: Relation, entities: Mapping[str, EntityEnvelope]
) -> None:
    """Validate actual local endpoints and evidence files against an entity catalog."""
    refs = [relation.source, *relation.resolution.candidates]
    if relation.resolution.target is not None:
        refs.append(relation.resolution.target)
    actual = []
    for ref in refs:
        entity = entities.get(ref.id)
        if (
            entity is None
            or entity.id != ref.id
            or entity.entity_type != ref.entity_type
        ):
            raise ValueError("missing endpoint or declared endpoint type mismatch")
        if entity.repository_id != relation.repository_id:
            raise ValueError("relation endpoints must belong to the same repository")
        actual.append(entity)
    if relation.relation_kind == RelationKind.CALLS:
        for entity in actual:
            if isinstance(entity, Symbol) and entity.symbol_kind not in (
                "METHOD",
                "CONSTRUCTOR",
            ):
                raise ValueError("CALLS requires callable symbols")
            if isinstance(entity, Operation) and entity.operation_kind != "CALL":
                raise ValueError("CALLS source operation must be CALL")
    if relation.relation_kind == RelationKind.DECLARES and (
        not isinstance(actual[0], Occurrence)
        or actual[0].occurrence_kind != "DECLARATION"
    ):
        raise ValueError("DECLARES requires a declaration occurrence")
    for evidence in relation.evidence:
        file = entities.get(evidence.source_range.source_file_id)
        if (
            not isinstance(file, SourceFile)
            or file.id != evidence.source_range.source_file_id
        ):
            raise ValueError("evidence must reference an existing source file")
        if file.repository_id != relation.repository_id:
            raise ValueError("evidence file must belong to the same repository")


class SymbolSelector(ContractModel):
    kind: Literal["SYMBOL"] = "SYMBOL"
    qualified_name: Text
    parameter_type_names: tuple[Text, ...] | None = None


class HttpSelector(ContractModel):
    kind: Literal["HTTP"] = "HTTP"
    method: Literal[
        "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"
    ]
    path: Text
    service: Text | None = None

    @model_validator(mode="after")
    def valid_path(self) -> Self:
        if not self.path.startswith("/") or any(c in self.path for c in ("?", "#")):
            raise ValueError(
                "HTTP path must start with / and exclude query and fragment"
            )
        return self


class DatabaseSelector(ContractModel):
    kind: Literal["DATABASE"] = "DATABASE"
    connection: Text
    schema_name: Text | None = None
    table: Text


ExternalSelector = Annotated[
    SymbolSelector | HttpSelector | DatabaseSelector, Field(discriminator="kind")
]


class ExternalReference(EntityEnvelope):
    entity_type: Literal[EntityType.EXTERNAL_REFERENCE] = EntityType.EXTERNAL_REFERENCE
    source: EntityRef
    selector: ExternalSelector
    repository_hint: Text | None = None
    version_hint: Text | None = None
    resolution: Literal["UNRESOLVED"] = "UNRESOLVED"
    reason: Text
    evidence: tuple[Evidence, ...] = Field(min_length=1)
    certainty: Certainty
    coverage: Coverage

    @model_validator(mode="after")
    def valid_external(self) -> Self:
        pairs = _RELATION_ENDPOINTS[RelationKind.EXTERNAL_DEPENDENCY]
        if (self.source.entity_type, self.entity_type) not in pairs:
            raise ValueError("invalid external dependency source type")
        if (
            self.coverage.status == "UNSUPPORTED"
            and self.certainty != Certainty.UNKNOWN
        ):
            raise ValueError("unsupported capability requires UNKNOWN certainty")
        return self


def validate_external_reference(
    reference: ExternalReference, entities: Mapping[str, EntityEnvelope]
) -> None:
    """Check local origin and evidence without consulting external repositories."""
    source = entities.get(reference.source.id)
    if (
        source is None
        or source.id != reference.source.id
        or source.entity_type != reference.source.entity_type
    ):
        raise ValueError("missing external reference source or source type mismatch")
    if source.repository_id != reference.repository_id:
        raise ValueError("external reference source must be local")
    for evidence in reference.evidence:
        file = entities.get(evidence.source_range.source_file_id)
        if (
            not isinstance(file, SourceFile)
            or file.id != evidence.source_range.source_file_id
        ):
            raise ValueError("external evidence must reference an existing source file")
        if file.repository_id != reference.repository_id:
            raise ValueError("external evidence file must be local")


Entity = Annotated[
    SourceFile
    | CodeEntity
    | Symbol
    | Scope
    | Occurrence
    | Operation
    | Value
    | Relation
    | ExternalReference,
    Field(discriminator="entity_type"),
]


class EntityDocument(RootModel[Entity]):
    """Validated discriminated entity document for JSON interchange."""


def entity_json_schema() -> dict:
    """Export the structural JSON Schema for an entity document."""
    return EntityDocument.model_json_schema()
