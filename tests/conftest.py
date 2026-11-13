from collections.abc import Callable
from uuid import UUID

import pytest

from code_crawler.ingestion import UcmBatch
from code_crawler.ucm import (
    CallableSignature,
    Certainty,
    CodeEntity,
    Coverage,
    DatabaseSelector,
    EntityRef,
    EntityType,
    Evidence,
    ExternalReference,
    HttpSelector,
    Occurrence,
    Operation,
    Position,
    Relation,
    RelationKind,
    Resolution,
    Scope,
    SourceFile,
    SourceRange,
    Symbol,
    SymbolSelector,
    TypeRef,
    Value,
    callable_key,
    logical_id,
)


@pytest.fixture
def ucm_batch_factory() -> Callable[[UUID], UcmBatch]:
    def build(repository: UUID) -> UcmBatch:
        repo = str(repository)

        def base(kind: EntityType, key: str) -> dict:
            return {
                "repository_id": repo,
                "logical_key": key,
                "name": key,
                "id": logical_id(repo, kind, key),
            }

        file = SourceFile(
            **base(EntityType.SOURCE_FILE, "A.java"),
            path="A.java",
            language="java",
            content_sha256="a" * 64,
        )
        loc = SourceRange(
            source_file_id=file.id,
            start=Position(line=1, byte_column=0),
            end=Position(line=2, byte_column=0),
        )
        class_symbol = Symbol(
            **base(EntityType.SYMBOL, "A"), symbol_kind="CLASS", qualified_name="A"
        )
        ref = TypeRef(name="A", resolution="RESOLVED", target_symbol_id=class_symbol.id)
        sig = CallableSignature(
            parameter_types=(ref, TypeRef(name="String")),
            return_type=TypeRef(name="void"),
        )
        key = callable_key("A", "m", sig)
        method = Symbol(
            **{**base(EntityType.SYMBOL, key), "name": "m"},
            symbol_kind="METHOD",
            qualified_name="A.m",
            owner_key="A",
            signature=sig,
            source_range=loc,
        )
        scope = Scope(
            **base(EntityType.SCOPE, "method-scope"),
            scope_kind="CALLABLE",
            owner_symbol_id=method.id,
        )
        # Cycle owner/scope is legal; only parent_scope cycles are prohibited.
        method = Symbol.model_validate(
            {**method.model_dump(), "scope_id": scope.id, "type_ref": ref}
        )
        occurrence = Occurrence(
            **base(EntityType.OCCURRENCE, "use"),
            occurrence_kind="REFERENCE",
            source_range=loc,
            scope_id=scope.id,
            resolution="RESOLVED",
            target_symbol_id=method.id,
        )
        unknown = Value(
            **base(EntityType.VALUE, "unknown"),
            value_kind="UNKNOWN",
            partial=True,
            type_ref=ref,
        )
        null = Value(
            **base(EntityType.VALUE, "null"), value_kind="LITERAL", literal=None
        )
        literal = Value(
            **base(EntityType.VALUE, "text"),
            value_kind="LITERAL",
            literal="select * from пользователи",
        )
        result = Value(
            **base(EntityType.VALUE, "result"), value_kind="SYMBOLIC", partial=True
        )
        operation = Operation(
            **base(EntityType.OPERATION, "call"),
            operation_kind="CALL",
            scope_id=scope.id,
            input_value_ids=(unknown.id, literal.id, unknown.id),
            output_value_ids=(result.id,),
            callee=TypeRef(
                name="A.m", resolution="RESOLVED", target_symbol_id=method.id
            ),
        )
        evidence = Evidence(
            source_range=loc,
            analyzer="java",
            analyzer_version="1",
            rule="ast.call",
            description="Static site",
        )
        coverage = Coverage(
            capability="java.calls",
            analyzer_version="1",
            status="PARTIAL",
            reasons=("dynamic dispatch", "missing dependency"),
        )
        relation = Relation(
            **base(EntityType.RELATION, "call-relation"),
            relation_kind=RelationKind.CALLS,
            source=EntityRef(id=operation.id, entity_type=operation.entity_type),
            resolution=Resolution(
                status="PARTIAL",
                candidates=(EntityRef(id=method.id, entity_type=method.entity_type),),
                reason="missing context",
            ),
            certainty=Certainty.INFERRED,
            evidence=(evidence, evidence),
            coverage=coverage,
        )
        externals = []
        for i, selector in enumerate(
            (
                SymbolSelector(qualified_name="lib.send"),
                SymbolSelector(qualified_name="lib.send", parameter_type_names=()),
                HttpSelector(method="POST", path="/users", service="users"),
                DatabaseSelector(connection="db", schema_name="Public", table="Users"),
            )
        ):
            externals.append(
                ExternalReference(
                    **base(EntityType.EXTERNAL_REFERENCE, f"external:{i}"),
                    source=EntityRef(
                        id=operation.id, entity_type=operation.entity_type
                    ),
                    selector=selector,
                    repository_hint="other",
                    version_hint="v1",
                    reason="external dependency",
                    evidence=(evidence,),
                    certainty=Certainty.STATIC_PROVEN,
                    coverage=coverage,
                )
            )
        legacy = CodeEntity(
            **base(EntityType.SQL_CANDIDATE, "sql"),
            entity_type=EntityType.SQL_CANDIDATE,
        )
        # Deliberately reverse order: references precede definitions.
        return UcmBatch(
            repository_id=repository,
            entities=tuple(
                reversed(
                    [
                        file,
                        class_symbol,
                        method,
                        scope,
                        occurrence,
                        unknown,
                        null,
                        literal,
                        result,
                        operation,
                        relation,
                        *externals,
                        legacy,
                    ]
                )
            ),
        )

    return build
