import asyncio
import hashlib
from uuid import UUID

import pytest
from pydantic import ValidationError

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_semantic import JavaSemanticAnalyzer
from code_crawler.ucm import (
    DataAccess,
    EntityType,
    Relation,
    RelationKind,
    SourceFile,
    SqlStatement,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")


def analyze(text: str, dialect: str = "postgres") -> UcmBatch:
    content = text.encode()
    file = SourceFile(
        repository_id=str(REPO),
        logical_key="A.java",
        name="A.java",
        path="A.java",
        language="java",
        id=logical_id(str(REPO), EntityType.SOURCE_FILE, "A.java"),
        content_sha256=hashlib.sha256(content).hexdigest(),
    )
    source = SourceInput(file, content)
    results = asyncio.run(JavaSemanticAnalyzer((source,), dialect)((source,)))
    batch = UcmBatch(repository_id=REPO, entities=(file, *results[0].entities))
    assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
    return batch


def statements(batch: UcmBatch) -> list[SqlStatement]:
    return [e for e in batch.entities if isinstance(e, SqlStatement)]


def execution_links(batch: UcmBatch) -> list[Relation]:
    return [
        e
        for e in batch.entities
        if isinstance(e, Relation)
        and e.relation_kind == RelationKind.EXECUTES_STATEMENT
    ]


def test_unused_statement_has_accesses_without_execution() -> None:
    batch = analyze('class A {void m(){String q="delete from t";}}')
    assert statements(batch) and any(isinstance(e, DataAccess) for e in batch.entities)
    assert execution_links(batch) == []


def test_execution_links_each_statement_without_mixing_effects() -> None:
    batch = analyze(
        'import java.sql.Statement; class A {void m(Statement s){s.execute("delete from t; select id from s");}}'
    )
    linked = execution_links(batch)
    assert len(linked) == 2 and all(r.resolution.status == "RESOLVED" for r in linked)
    by_id = {s.id: s for s in statements(batch)}
    assert {by_id[r.resolution.target.id].operation for r in linked} == {
        "DELETE",
        "SELECT",
    }
    for statement in statements(batch):
        facts = [
            e
            for e in batch.entities
            if isinstance(e, DataAccess) and e.statement_id == statement.id
        ]
        assert {a.table_name.text for a in facts if a.table_name} == (
            {"t"} if statement.operation == "DELETE" else {"s"}
        )


def test_dynamic_fragments_have_no_invented_ast_accesses() -> None:
    batch = analyze(
        'import java.sql.Statement; class A {void m(Statement s,String table){s.execute("select id from "+table);}}'
    )
    linked = execution_links(batch)
    assert linked and all(r.resolution.status != "RESOLVED" for r in linked)
    partial_ids = {s.id for s in statements(batch) if s.parse_status == "PARTIAL"}
    assert partial_ids
    assert not any(
        isinstance(a, DataAccess) and a.statement_id in partial_ids
        for a in batch.entities
    )
    assert not any(
        isinstance(a, DataAccess)
        and a.table_name
        and a.table_name.text == "__unknown__"
        for a in batch.entities
    )


def test_alternative_variants_are_possible_statement_targets() -> None:
    batch = analyze(
        'import java.sql.Statement; class A {void m(Statement s,boolean flag){String q=flag?"select id from a":"select id from b";s.execute(q);}}'
    )
    assert execution_links(batch)
    assert all(r.resolution.status == "PARTIAL" for r in execution_links(batch))


def test_prepared_unknown_origin_has_unresolved_statement_edge() -> None:
    batch = analyze(
        "import java.sql.PreparedStatement; class A {void m(PreparedStatement p){p.execute();}}"
    )
    assert execution_links(batch)[0].resolution.status == "UNRESOLVED"
    assert not statements(batch)


def test_error_statement_kept_and_execution_is_not_definite_ast() -> None:
    batch = analyze(
        'import java.sql.Statement; class A {void m(Statement s){s.execute("select * from ; delete from t");}}'
    )
    linked = execution_links(batch)
    assert {r.resolution.status for r in linked} == {"PARTIAL", "RESOLVED"}
    assert {s.parse_status for s in statements(batch)} == {"ERROR", "COMPLETE"}


def test_dialect_profile_changes_fingerprint_and_quotes() -> None:
    batch = analyze('class A {void m(){String q="select `ID` from `Users`";}}', "mysql")
    assert all(s.dialect == "mysql" for s in statements(batch))
    assert any(
        isinstance(e, DataAccess)
        and e.table_name
        and e.table_name.quoted
        and e.table_name.text == "Users"
        for e in batch.entities
    )
    assert (
        JavaSemanticAnalyzer((), "postgres").analysis_version
        != JavaSemanticAnalyzer((), "mysql").analysis_version
    )


def test_statement_slice_and_access_contract_are_validated() -> None:
    batch = analyze('class A {void m(){String q="select id from t";}}')
    statement = statements(batch)[0]
    bad = statement.model_copy(update={"text": "x" * len(statement.text)})
    with pytest.raises(ValidationError, match="candidate slice"):
        UcmBatch(
            repository_id=REPO,
            entities=tuple(bad if e.id == bad.id else e for e in batch.entities),
        )
    access = next(e for e in batch.entities if isinstance(e, DataAccess))
    bad_access = access.model_copy(update={"access_kind": "DELETE"})
    with pytest.raises(ValidationError, match="statement and effect"):
        UcmBatch(
            repository_id=REPO,
            entities=tuple(
                bad_access if e.id == bad_access.id else e for e in batch.entities
            ),
        )
