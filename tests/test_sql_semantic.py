import pytest

from code_crawler.sql_semantic import analyze_statements


def accesses(query: str, dialect: str = "postgres") -> list:
    result = analyze_statements(query, dialect)
    assert len(result) == 1
    assert result[0].parse_status == "COMPLETE", result[0].reasons
    return list(result[0].accesses)


def table_effects(query: str, dialect: str = "postgres") -> set[tuple[str, str]]:
    return {
        (a.table_name.text, a.access_kind)
        for a in accesses(query, dialect)
        if a.table_name and a.object_kind == "TABLE"
    }


def test_statements_do_not_mix_effects_or_split_strings_and_comments() -> None:
    query = "delete from t; /* ; */ select ';' as value from s; update u set a=1"
    statements = analyze_statements(query)
    assert [s.operation for s in statements] == ["DELETE", "SELECT", "UPDATE"]
    assert [
        {a.table_name.text for a in s.accesses if a.table_name} for s in statements
    ] == [{"t"}, {"s"}, {"u"}]
    assert all(query[s.text_start : s.text_end] == s.text for s in statements)


def test_quoted_parts_and_case_are_preserved() -> None:
    facts = accesses('select u."UserID", u.Mixed from "Db"."App"."Users" u')
    column = next(a for a in facts if a.column_name and a.column_name.text == "UserID")
    assert column.column_name.quoted and column.column_name.normalized == "UserID"
    assert (
        column.catalog_name.text,
        column.schema_name.text,
        column.table_name.text,
    ) == ("Db", "App", "Users")
    assert (
        next(
            a for a in facts if a.column_name and a.column_name.text == "Mixed"
        ).column_name.normalized
        == "mixed"
    )
    assert all(a.resolution == "UNRESOLVED" for a in facts)


def test_dotted_quoted_name_is_one_part() -> None:
    fact = next(a for a in accesses('select "a.b" from "x.y"') if a.column_name)
    assert fact.table_name.text == "x.y" and fact.schema_name is None
    assert fact.column_name.text == "a.b"


def test_join_unqualified_column_is_ambiguous() -> None:
    facts = accesses("select a.id,b.id,missing from a join b on a.id=b.id")
    unknown = next(
        a for a in facts if a.column_name and a.column_name.text == "missing"
    )
    assert unknown.binding_status == "AMBIGUOUS" and unknown.table_name is None
    assert unknown.resolution == "AMBIGUOUS"
    assert {
        a.table_name.text for a in facts if a.column_name and a.column_name.text == "id"
    } == {"a", "b"}


def test_cte_alias_is_not_a_physical_table() -> None:
    assert table_effects("with c as (select id from real_t) select c.id from c") == {
        ("real_t", "READ")
    }
    outer = [
        a
        for a in accesses("with c as (select id from real_t) select c.id from c")
        if a.qualifier and a.qualifier.text == "c"
    ]
    assert outer and outer[0].binding_status == "UNBOUND"


def test_nested_cte_shadowing() -> None:
    query = "with c as (select id from outer_t) select * from c where exists(with c as (select id from inner_t) select 1 from c)"
    assert table_effects(query) == {("outer_t", "READ"), ("inner_t", "READ")}


def test_derived_and_correlated_sources() -> None:
    query = "select q.id from (select id from base_t) q where exists(select 1 from other_t b where b.id=q.id)"
    assert table_effects(query) == {("base_t", "READ"), ("other_t", "READ")}
    assert any(a.column_name and a.binding_status == "UNBOUND" for a in accesses(query))


def test_union_sources_remain_local() -> None:
    assert table_effects("select a from t union all select b from s") == {
        ("t", "READ"),
        ("s", "READ"),
    }


def test_update_from_separates_target_and_predicate_reads() -> None:
    facts = accesses(
        "update target t set value=s.value+1 from source s where t.id=s.id"
    )
    assert any(
        a.access_kind == "UPDATE"
        and a.table_name.text == "target"
        and a.column_name
        and a.column_name.text == "value"
        for a in facts
    )
    assert any(
        a.access_kind == "READ"
        and a.table_name.text == "source"
        and a.column_name
        and a.column_name.text == "value"
        for a in facts
    )
    assert ("source", "UPDATE") not in table_effects(
        "update target t set value=s.value from source s where t.id=s.id"
    )


def test_insert_select_and_conflict_update() -> None:
    query = "insert into dst(id,value) select id,value from src on conflict(id) do update set value=excluded.value"
    effects = table_effects(query)
    assert {("dst", "INSERT"), ("dst", "UPDATE"), ("src", "READ")} <= effects
    assert all(a.table_name.text != "excluded" for a in accesses(query) if a.table_name)


def test_merge_actions_and_columns() -> None:
    query = "merge into dst d using src s on d.id=s.id when matched then update set value=s.value when not matched then insert(id,value) values(s.id,s.value)"
    effects = table_effects(query)
    assert {
        ("dst", "MERGE"),
        ("dst", "UPDATE"),
        ("dst", "INSERT"),
        ("src", "READ"),
    } <= effects
    assert any(
        a.column_name and a.column_name.text == "value" and a.access_kind == "UPDATE"
        for a in accesses(query)
    )


def test_delete_using_does_not_delete_source() -> None:
    effects = table_effects("delete from dst using src where dst.id=src.id")
    assert ("dst", "DELETE") in effects and ("src", "READ") in effects
    assert ("src", "DELETE") not in effects


@pytest.mark.parametrize(
    "query",
    [
        'create table "T"(id int)',
        'alter table "T" add column value int',
        'drop table "T"',
        'truncate table "T"',
    ],
)
def test_basic_ddl(query: str) -> None:
    assert ("T", "DDL") in table_effects(query)


def test_stars_and_using_are_explicitly_unresolved() -> None:
    facts = accesses("select *,a.* from a join b using(id)")
    assert any(
        a.column_name and a.column_name.text == "*" and a.table_name is None
        for a in facts
    )
    assert any(
        a.column_name and a.column_name.text == "id" and a.binding_status == "AMBIGUOUS"
        for a in facts
    )


def test_static_unknown_identifier_is_not_a_dynamic_placeholder() -> None:
    assert ("__unknown__", "READ") in table_effects('select id from "__unknown__"')


def test_parse_error_does_not_discard_valid_following_statement() -> None:
    result = analyze_statements("select * from ; delete from t")
    assert [s.parse_status for s in result] == ["ERROR", "COMPLETE"]
    assert result[0].accesses == () and result[1].operation == "DELETE"


def test_unknown_statement_is_retained_without_effects() -> None:
    result = analyze_statements("begin; select id from t; commit")
    assert [s.parse_status for s in result] == [
        "UNSUPPORTED",
        "COMPLETE",
        "UNSUPPORTED",
    ]
    assert not result[0].accesses and not result[2].accesses


@pytest.mark.parametrize(
    ("query", "dialect", "name"),
    [
        ("select `ID` from `Users`", "mysql", "Users"),
        ("select [ID] from [Users]", "tsql", "Users"),
    ],
)
def test_explicit_dialect_profiles(query: str, dialect: str, name: str) -> None:
    assert (name, "READ") in table_effects(query, dialect)


def test_unsupported_profile_rejected() -> None:
    with pytest.raises(ValueError, match="dialect"):
        analyze_statements("select id from t", "guess")


def test_mysql_joined_update_target_is_not_assumed_to_be_first_table() -> None:
    facts = accesses("update a join b on a.id=b.id set b.value=1", "mysql")
    assert any(
        a.access_kind == "UPDATE" and a.column_name and a.table_name.text == "b"
        for a in facts
    )


def test_cte_casefolding_and_nonrecursive_self_name() -> None:
    assert table_effects("with C as (select id from real_t) select id from c") == {
        ("real_t", "READ")
    }
    assert table_effects("with t as (select id from t) select id from t") == {
        ("t", "READ")
    }


def test_recursive_cte_keeps_seed_without_fake_recursive_table() -> None:
    assert table_effects(
        "with recursive c as (select id from seed union all select id from c) select * from c"
    ) == {("seed", "READ")}


def test_output_alias_does_not_become_a_base_column() -> None:
    facts = accesses("select id as label from t order by label")
    label = next(a for a in facts if a.column_name and a.column_name.text == "label")
    assert label.table_name is None and label.binding_status == "UNBOUND"


def test_tuple_update_and_implicit_insert_columns() -> None:
    facts = accesses("update t set (a,b)=(1,2)")
    assert {
        a.column_name.text for a in facts if a.access_kind == "UPDATE" and a.column_name
    } == {"a", "b"}
    assert any(
        a.access_kind == "INSERT" and a.column_name and a.column_name.text == "*"
        for a in accesses("insert into t values(1)")
    )


def test_ddl_column_definitions_and_namespace_unsupported() -> None:
    assert any(
        a.access_kind == "DDL" and a.column_name and a.column_name.text == "value"
        for a in accesses("alter table t add column value int")
    )
    assert analyze_statements("create schema example")[0].parse_status == "UNSUPPORTED"


def test_utf8_decoded_offsets_and_dollar_quoted_semicolon() -> None:
    query = "select $$привет;мир$$ from t; delete from u"
    result = analyze_statements(query)
    assert len(result) == 2
    assert all(query[s.text_start : s.text_end] == s.text for s in result)


def test_quoted_escaped_and_whitespace_identifier() -> None:
    facts = accesses('select "a""b", " " from " "')
    assert {a.column_name.text for a in facts if a.column_name} == {'a"b', " "}
    assert all(a.table_name.text == " " for a in facts if a.table_name)


def test_mysql_join_does_not_write_the_first_table_without_assignment() -> None:
    assert ("a", "UPDATE") not in table_effects(
        "update a join b on a.id=b.id set b.value=1", "mysql"
    )


def test_merge_delete_and_conflict_do_nothing() -> None:
    assert ("dst", "DELETE") in table_effects(
        "merge into dst using src on dst.id=src.id when matched then delete"
    )
    assert ("dst", "UPDATE") not in table_effects(
        "insert into dst(id) values(1) on conflict(id) do nothing"
    )


def test_trailing_comments_and_empty_segments_do_not_create_error_statements() -> None:
    result = analyze_statements(
        ";; select id from t; /* only a comment; */ ; -- trailing comment"
    )
    assert len(result) == 1 and result[0].parse_status == "COMPLETE"


def test_create_as_select_and_alter_drop_column_effects() -> None:
    effects = table_effects("create table dst as select id from src")
    assert {("dst", "DDL"), ("dst", "INSERT"), ("src", "READ")} <= effects
    facts = accesses("alter table t drop column value")
    assert any(
        a.column_name and a.column_name.text == "value" and a.access_kind == "DDL"
        for a in facts
    )
    assert not any(
        a.column_name and a.column_name.text == "value" and a.access_kind == "READ"
        for a in facts
    )
