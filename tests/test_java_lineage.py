import asyncio
import hashlib
from uuid import UUID

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_lineage import JavaLineageAnalyzer
from code_crawler.ucm import (
    EntityType,
    Relation,
    RelationKind,
    SourceFile,
    SqlBinding,
    SqlExecute,
    SqlPlaceholder,
    logical_id,
)

REPO = UUID("11111111-1111-1111-1111-111111111111")


def analyze(
    body: str,
    imports: str = "import java.sql.Connection; import java.sql.PreparedStatement;",
    params: str = "Connection c,int id",
    dialect: str = "postgres",
) -> UcmBatch:
    text = imports + " class A {void m(" + params + "){" + body + "}}"
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
    results = asyncio.run(JavaLineageAnalyzer((source,), dialect)((source,)))
    batch = UcmBatch(repository_id=REPO, entities=(file, *results[0].entities))
    assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
    return batch


def bindings(batch: UcmBatch) -> list[SqlBinding]:
    return [e for e in batch.entities if isinstance(e, SqlBinding)]


def values(batch: UcmBatch) -> list:
    catalog = {e.id: e for e in batch.entities}
    return [catalog[b.value_id] for b in bindings(batch)]


def relations(batch: UcmBatch, kind: RelationKind) -> list[Relation]:
    return [
        e for e in batch.entities if isinstance(e, Relation) and e.relation_kind == kind
    ]


def test_java_symbol_to_binding_placeholder_column_chain() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("select name from users where id=?");p.setInt(1,id);p.executeQuery();'
    )
    assert len(bindings(batch)) == 1 and bindings(batch)[0].status == "BOUND"
    assert values(batch)[0].value_kind == "SYMBOLIC"
    assert relations(batch, RelationKind.VALUE_OF)
    assert (
        relations(batch, RelationKind.BINDS_PARAMETER)[0].resolution.status
        == "RESOLVED"
    )
    assert (
        relations(batch, RelationKind.PARAMETER_COLUMN)[0].resolution.status
        == "RESOLVED"
    )


def test_last_setter_and_execution_snapshots() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("delete from t where id=?");p.setInt(1,1);p.setInt(1,2);p.execute();p.setInt(1,3);p.execute();'
    )
    assert sorted(v.literal for v in values(batch)) == [2, 3]
    assert len([e for e in batch.entities if isinstance(e, SqlExecute)]) == 2


def test_clear_parameters_and_missing_binding_are_explicit() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("delete from t where id=?");p.setInt(1,1);p.clearParameters();p.execute();'
    )
    assert bindings(batch)[0].status == "MISSING"
    assert values(batch)[0].value_kind == "UNKNOWN"
    assert (
        relations(batch, RelationKind.BINDS_PARAMETER)[0].resolution.status == "PARTIAL"
    )


def test_alias_preserves_binding_state() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("delete from t where id=?");PreparedStatement a=p;a.setInt(1,5);p.execute();'
    )
    assert values(batch)[0].literal == 5


def test_value_reassignment_after_setter_does_not_change_binding() -> None:
    batch = analyze(
        'int x=id; PreparedStatement p=c.prepareStatement("delete from t where id=?");p.setInt(1,x);x=42;p.execute();'
    )
    assert values(batch)[0].value_kind == "SYMBOLIC"
    assert values(batch)[0].literal is None


def test_unknown_index_does_not_reuse_previous_value() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("delete from t where id=?");p.setInt(1,5);p.setInt(id,7);p.execute();'
    )
    assert all(v.literal != 5 for v in values(batch))
    assert any(b.binding_kind == "UNKNOWN" for b in bindings(batch))
    assert not any(
        r.resolution.status == "RESOLVED"
        for r in relations(batch, RelationKind.BINDS_PARAMETER)
    )


def test_set_null_implies_null_not_sql_type() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("update t set x=?");p.setNull(1,12);p.execute();'
    )
    assert values(batch)[0].value_kind == "LITERAL" and values(batch)[0].literal is None


def test_unknown_sql_origin_keeps_binding_without_guessed_parameter() -> None:
    batch = analyze(
        "p.setInt(1,id);p.execute();", params="Connection c,int id,PreparedStatement p"
    )
    assert bindings(batch) and not [
        e for e in batch.entities if isinstance(e, SqlPlaceholder)
    ]
    assert (
        relations(batch, RelationKind.BINDS_PARAMETER)[0].resolution.status
        == "UNRESOLVED"
    )


def test_branches_are_partial_binding_snapshots() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("delete from t where id=?");if(id>0){p.setInt(1,1);}else{p.setInt(1,2);}p.execute();'
    )
    assert {v.literal for v in values(batch)} == {1, 2}
    assert all(b.status == "PARTIAL" for b in bindings(batch))


def test_statements_use_global_jdbc_positions() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("delete from a where id=?; delete from b where id=?");p.setInt(1,10);p.setInt(2,20);p.execute();'
    )
    assert {e.position for e in batch.entities if isinstance(e, SqlPlaceholder)} == {
        1,
        2,
    }
    assert len(relations(batch, RelationKind.BINDS_PARAMETER)) == 2
    assert all(
        r.resolution.status == "RESOLVED"
        for r in relations(batch, RelationKind.BINDS_PARAMETER)
    )


def test_spring_scalar_varargs_and_inline_array() -> None:
    batch = analyze(
        'j.update("update t set a=? where id=?", "name",id);j.update("delete from t where id=?",new Object[]{id});',
        imports="import org.springframework.jdbc.core.JdbcTemplate;",
        params="JdbcTemplate j,int id",
    )
    assert len(bindings(batch)) == 3
    assert any(v.literal == "name" for v in values(batch))
    assert all(
        r.resolution.status == "RESOLVED"
        for r in relations(batch, RelationKind.BINDS_PARAMETER)
    )


def test_spring_named_map_repeated_placeholders() -> None:
    batch = analyze(
        'j.update("delete from t where id=:id or parent_id=:id",Map.of("id",id));',
        imports="import java.util.Map; import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;",
        params="NamedParameterJdbcTemplate j,int id",
    )
    assert len(bindings(batch)) == 1
    assert len(relations(batch, RelationKind.BINDS_PARAMETER)) == 2
    assert all(
        r.resolution.status == "RESOLVED"
        for r in relations(batch, RelationKind.BINDS_PARAMETER)
    )


def test_mutable_map_and_parameter_source() -> None:
    batch = analyze(
        'Map<String,Object> m=new HashMap<>();m.put("id",id);j.update("delete from t where id=:id",m);m.put("id",3);j.update("delete from t where id=:id",m);',
        imports="import java.util.Map; import java.util.HashMap; import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;",
        params="NamedParameterJdbcTemplate j,int id",
    )
    assert len(bindings(batch)) == 2
    assert {v.value_kind for v in values(batch)} == {"LITERAL", "SYMBOLIC"}
    assert any(v.literal == 3 for v in values(batch))


def test_map_sql_parameter_source_chain() -> None:
    batch = analyze(
        'j.update("delete from t where id=:id",new MapSqlParameterSource().addValue("id",id));',
        imports="import org.springframework.jdbc.core.namedparam.MapSqlParameterSource; import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;",
        params="NamedParameterJdbcTemplate j,int id",
    )
    assert len(bindings(batch)) == 1 and values(batch)[0].value_kind == "SYMBOLIC"
    assert (
        relations(batch, RelationKind.BINDS_PARAMETER)[0].resolution.status
        == "RESOLVED"
    )


def test_dynamic_sql_has_no_guessed_placeholders() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("select id from "+table+" where id=?");p.setInt(1,id);p.execute();',
        params="Connection c,int id,String table",
    )
    assert not any(
        isinstance(e, SqlPlaceholder) and e.token_text == "?" for e in batch.entities
    )
    assert (
        relations(batch, RelationKind.BINDS_PARAMETER)[0].resolution.status
        == "UNRESOLVED"
    )


def test_named_map_clear_and_unknown_mutation_do_not_keep_stale_values() -> None:
    batch = analyze(
        'Map<String,Object> m=new HashMap<>();m.put("id",7);m.clear();j.update("delete from t where id=:id",m);',
        imports="import java.util.Map; import java.util.HashMap; import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;",
        params="NamedParameterJdbcTemplate j,int id",
    )
    assert all(v.literal != 7 for v in values(batch))
    assert bindings(batch)[0].status == "MISSING"


def test_collection_expansion_remains_partial() -> None:
    batch = analyze(
        'j.update("delete from t where id in (:ids)",Map.of("ids",ids));',
        imports="import java.util.Map; import java.util.List; import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;",
        params="NamedParameterJdbcTemplate j,List<Integer> ids",
    )
    assert bindings(batch)[0].status == "PARTIAL"
    assert "collection" in " ".join(bindings(batch)[0].reasons)


def test_increment_cannot_reuse_stale_scalar_literal() -> None:
    batch = analyze(
        'int x=1;x++;PreparedStatement p=c.prepareStatement("delete from t where id=?");p.setInt(1,x);p.execute();'
    )
    assert values(batch)[0].value_kind == "UNKNOWN"


def test_external_field_does_not_resolve_to_same_named_own_field() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("delete from t where id=?");p.setObject(1,other.id);p.execute();',
        params="Connection c,int id,Object other",
    )
    assert not relations(batch, RelationKind.VALUE_OF)
    assert values(batch)[0].value_kind == "UNKNOWN"


def test_bindings_after_escape_are_not_reused() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("delete from t where id=?");p.setInt(1,7);external(p);p.execute();'
    )
    assert not any(v.literal == 7 for v in values(batch))


def test_named_map_can_be_reused_across_executions() -> None:
    batch = analyze(
        'Map<String,Object> m=Map.of("id",id);j.update("delete from a where id=:id",m);j.update("delete from b where id=:id",m);',
        imports="import java.util.Map; import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;",
        params="NamedParameterJdbcTemplate j,int id",
    )
    assert len(bindings(batch)) == 2
    assert all(b.status == "BOUND" for b in bindings(batch))


def test_signed_numeric_boolean_and_reaching_definitions() -> None:
    batch = analyze(
        'PreparedStatement p=c.prepareStatement("update t set a=?,b=?");int n=-5;p.setInt(1,n);p.setBoolean(2,true);p.execute();'
    )
    assert {v.literal for v in values(batch)} == {-5, True}


def test_invalid_binding_position_cannot_pass_batch_validation() -> None:
    import pytest
    from pydantic import ValidationError

    batch = analyze(
        'PreparedStatement p=c.prepareStatement("delete from t where id=?");p.setInt(1,id);p.execute();'
    )
    binding = bindings(batch)[0]
    altered = binding.model_copy(update={"position": 2})
    with pytest.raises(ValidationError, match="selector must match"):
        UcmBatch(
            repository_id=REPO,
            entities=tuple(
                altered if e.id == binding.id else e for e in batch.entities
            ),
        )
