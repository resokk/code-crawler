import asyncio
import hashlib
from uuid import UUID

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_execution import JavaExecutionAnalyzer
from code_crawler.ucm import (
    EntityType,
    Operation,
    Relation,
    RelationKind,
    SourceFile,
    SqlConstruction,
    SqlExecute,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")


def analyze(text: str) -> UcmBatch:
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
    results = asyncio.run(JavaExecutionAnalyzer((source,))((source,)))
    batch = UcmBatch(repository_id=REPO, entities=(file, *results[0].entities))
    assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
    return batch


def executions(batch: UcmBatch) -> list[SqlExecute]:
    return [e for e in batch.entities if isinstance(e, SqlExecute)]


def links(batch: UcmBatch) -> list[Relation]:
    return [
        e
        for e in batch.entities
        if isinstance(e, Relation)
        and e.relation_kind == RelationKind.USES_SQL_CONSTRUCTION
    ]


def targets(batch: UcmBatch) -> set[str]:
    ids = {r.resolution.target.id for r in links(batch) if r.resolution.target}
    ids.update(c.id for r in links(batch) for c in r.resolution.candidates)
    return {
        v.text
        for e in batch.entities
        if isinstance(e, SqlConstruction) and e.id in ids
        for v in e.variants
    }


def test_discovery_and_preparation_do_not_execute() -> None:
    batch = analyze(
        'import java.sql.*; class A {void m(Connection c){String q="delete from t"; PreparedStatement p=c.prepareStatement(q);}}'
    )
    assert not executions(batch)


def test_direct_statement_execution_and_arguments() -> None:
    batch = analyze(
        'import java.sql.Statement; class A {void m(Statement s){s.executeUpdate("delete from t");}}'
    )
    assert len(executions(batch)) == 1
    assert executions(batch)[0].sql_argument_index == 0
    assert targets(batch) == {"delete from t"}
    assert links(batch)[0].resolution.status == "RESOLVED"
    call = next(e for e in batch.entities if isinstance(e, Operation))
    assert len(call.input_value_ids) == 1


def test_prepared_sql_is_captured_before_reassignment() -> None:
    batch = analyze(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c){String q="select * from t"; PreparedStatement p=c.prepareStatement(q); q="delete from other";p.executeQuery();}}'
    )
    assert len(executions(batch)) == 1
    assert targets(batch) == {"select * from t"}
    assert executions(batch)[0].sql_argument_index is None
    assert len(links(batch)[0].evidence) == 2


def test_no_name_only_sinks() -> None:
    batch = analyze(
        'class Statement {void execute(String x){}} class A {void m(Statement s,Object unknown){s.execute("delete from t");unknown.update("delete from t");}}'
    )
    assert not executions(batch)


def test_unknown_prepared_origin_is_explicit() -> None:
    batch = analyze(
        "import java.sql.PreparedStatement; class A {void m(PreparedStatement p){p.execute();}}"
    )
    assert len(executions(batch)) == 1
    assert links(batch)[0].resolution.status == "UNRESOLVED"


def test_alias_and_close_invalidate_all_aliases() -> None:
    batch = analyze(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c){PreparedStatement p=c.prepareStatement("select * from t");PreparedStatement alias=p;alias.execute();alias.close();p.execute();}}'
    )
    assert len(executions(batch)) == 2
    assert [r.resolution.status for r in links(batch)] == ["RESOLVED", "UNRESOLVED"]


def test_prepared_reassignment_does_not_reuse_old_sql() -> None:
    batch = analyze(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c,PreparedStatement external){PreparedStatement p=c.prepareStatement("select * from t");p=external;p.execute();}}'
    )
    assert links(batch)[0].resolution.status == "UNRESOLVED"


def test_inline_preparation_and_var() -> None:
    batch = analyze(
        'import java.sql.Connection; class A {void m(Connection c){c.prepareStatement("select * from t").executeQuery();var p=c.prepareStatement("delete from t");p.executeUpdate();}}'
    )
    assert len(executions(batch)) == 2
    assert targets(batch) == {"select * from t", "delete from t"}


def test_spring_sql_overloads_and_callback_exclusion() -> None:
    batch = analyze(
        'import org.springframework.jdbc.core.JdbcTemplate; class A {void m(JdbcTemplate j, Object mapper,Object callback){j.query("select * from t",mapper);j.update("delete from t");j.execute(callback);j.execute("delete from x");}}'
    )
    assert len(executions(batch)) == 3
    assert targets(batch) == {"select * from t", "delete from t", "delete from x"}


def test_batch_is_execution_without_guessed_queue() -> None:
    batch = analyze(
        'import java.sql.Statement; class A {void m(Statement s){s.addBatch("delete from t");s.executeBatch();}}'
    )
    assert len(executions(batch)) == 1
    assert links(batch)[0].resolution.status == "UNRESOLVED"
    assert "batch" in links(batch)[0].resolution.reason


def test_escaped_prepared_handle_is_unknown() -> None:
    batch = analyze(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c){PreparedStatement p=c.prepareStatement("select * from t");external(p);p.execute();}}'
    )
    assert links(batch)[0].resolution.status == "UNRESOLVED"


def test_branches_preserve_possible_origins() -> None:
    batch = analyze(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c,boolean flag){PreparedStatement p; if(flag){p=c.prepareStatement("select * from a");}else{p=c.prepareStatement("select * from b");}p.execute();}}'
    )
    assert len(executions(batch)) == 1
    assert targets(batch) == {"select * from a", "select * from b"}
    assert links(batch)[0].resolution.status == "PARTIAL"


def test_scoped_alias_shadowing() -> None:
    batch = analyze(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c){PreparedStatement p=c.prepareStatement("select * from outer_t"); {PreparedStatement p=c.prepareStatement("select * from inner_t");p.execute();}p.execute();}}'
    )
    assert len(executions(batch)) == 2
    assert targets(batch) == {"select * from inner_t", "select * from outer_t"}
    assert all(r.resolution.status == "RESOLVED" for r in links(batch))


def test_partial_dynamic_sql_and_unknown_sql_argument() -> None:
    batch = analyze(
        'import java.sql.Statement; class A {void m(Statement s,String table,String unknown){s.execute("select * from "+table);s.execute(unknown);}}'
    )
    assert len(executions(batch)) == 2
    assert [r.resolution.status for r in links(batch)] == ["PARTIAL", "UNRESOLVED"]


def test_builder_argument_is_evaluated_once() -> None:
    batch = analyze(
        'import java.sql.Statement; class A {void m(Statement s){StringBuilder b=new StringBuilder("select * from ");s.execute(b.append("t").toString());s.execute(b.toString());}}'
    )
    assert len(executions(batch)) == 2
    assert targets(batch) == {"select * from t"}
    assert all(r.resolution.status == "RESOLVED" for r in links(batch))


def test_factory_statement_and_fully_qualified_types() -> None:
    batch = analyze(
        'class A {void m(java.sql.Connection c){c.createStatement().execute("delete from a");var s=c.createStatement();s.executeQuery("select * from b");}}'
    )
    assert len(executions(batch)) == 2
    assert targets(batch) == {"delete from a", "select * from b"}


def test_spring_named_parameters_and_batches() -> None:
    batch = analyze(
        'import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations; class A {void m(NamedParameterJdbcOperations j,Object params,Object type){j.queryForObject("select * from t",params,type);j.batchUpdate("delete from t",params);}}'
    )
    assert len(executions(batch)) == 2
    assert links(batch)[0].resolution.status == "RESOLVED"
    assert links(batch)[1].resolution.status == "UNRESOLVED"


def test_field_escape_invalidates_prepared_origin() -> None:
    batch = analyze(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {PreparedStatement field;void m(Connection c){PreparedStatement p=c.prepareStatement("select * from t");this.field=p;p.execute();}}'
    )
    assert links(batch)[0].resolution.status == "UNRESOLVED"


def test_switch_origin_is_not_a_definite_target() -> None:
    batch = analyze(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c,int n){PreparedStatement p;switch(n){case 1:p=c.prepareStatement("select * from a");break;default:p=c.prepareStatement("select * from b");}p.execute();}}'
    )
    assert links(batch)[0].resolution.status == "UNRESOLVED"
    assert "switch" in links(batch)[0].resolution.reason


def test_same_named_type_in_library_package_is_not_trusted() -> None:
    batch = analyze(
        'package java.sql; class Statement {void execute(String x){}} class A {void m(Statement s){s.execute("delete from t");}}'
    )
    assert not executions(batch)


def test_nested_unknown_call_argument_invalidates_handle() -> None:
    batch = analyze(
        'import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c,boolean flag,PreparedStatement other){PreparedStatement p=c.prepareStatement("select * from t");external(flag?p:other);p.execute();}}'
    )
    assert links(batch)[0].resolution.status == "UNRESOLVED"


def test_jpql_and_native_orm_are_outside_jdbc_profile() -> None:
    batch = analyze(
        'class A {void m(Object em){em.createQuery("select x from User x").getResultList();em.createNativeQuery("select * from t").getResultList();}}'
    )
    assert not executions(batch)


def test_execution_contract_rejects_invalid_argument_and_owner() -> None:
    import pytest
    from pydantic import ValidationError

    batch = analyze(
        'import java.sql.Statement; class A {void m(Statement s){s.execute("delete from t");} void other(){}}'
    )
    execution = executions(batch)[0]
    invalid = execution.model_copy(update={"sql_argument_index": 2})
    with pytest.raises(ValidationError, match="outside CALL inputs"):
        UcmBatch(
            repository_id=REPO,
            entities=tuple(
                invalid if e.id == execution.id else e for e in batch.entities
            ),
        )
    other = next(
        e
        for e in batch.entities
        if e.entity_type == EntityType.SYMBOL and e.name == "other"
    )
    invalid = execution.model_copy(update={"owner_symbol_id": other.id})
    with pytest.raises(ValidationError, match="owner scope"):
        UcmBatch(
            repository_id=REPO,
            entities=tuple(
                invalid if e.id == execution.id else e for e in batch.entities
            ),
        )


def test_unknown_prepared_sql_keeps_preparation_evidence() -> None:
    batch = analyze(
        "import java.sql.Connection; import java.sql.PreparedStatement; class A {void m(Connection c,String sql){PreparedStatement p=c.prepareStatement(sql);p.execute();}}"
    )
    assert links(batch)[0].resolution.status == "UNRESOLVED"
    assert len(links(batch)[0].evidence) == 2
