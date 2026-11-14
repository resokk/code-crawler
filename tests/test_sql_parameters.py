import pytest

from code_crawler.sql_parameters import analyze_parameters


def test_jdbc_assignment_and_predicate_columns() -> None:
    parameters = analyze_parameters("update t set name=? where id=?")
    assert [p.position for p in parameters] == [1, 2]
    assert [
        [(c.column_name.text, c.access_kind) for c in p.columns] for p in parameters
    ] == [[("name", "UPDATE")], [("id", "READ")]]


def test_insert_rows_use_occurrence_position_not_ast_equality() -> None:
    parameters = analyze_parameters("insert into t(a,b) values(?,?),(?,?)")
    assert [p.position for p in parameters] == [1, 2, 3, 4]
    assert [[c.column_name.text for c in p.columns] for p in parameters] == [
        ["a"],
        ["b"],
        ["a"],
        ["b"],
    ]


def test_named_repeated_and_indexed_parameters() -> None:
    named = analyze_parameters("select id from t where id=:id or parent_id=:id")
    assert [p.parameter_name for p in named] == ["id", "id"]
    assert [[c.column_name.text for c in p.columns] for p in named] == [
        ["id"],
        ["parent_id"],
    ]
    indexed = analyze_parameters("select id from t where id=$2 and parent_id=$1")
    assert [p.position for p in indexed] == [2, 1]


def test_json_operator_strings_and_comments_are_not_bindings() -> None:
    query = "select data ? 'key', ':fake', '?' from t where id=? /* ? :fake */"
    parameters = analyze_parameters(query)
    assert len(parameters) == 1 and parameters[0].position == 1
    assert query[parameters[0].text_start : parameters[0].text_end] == "?"


def test_nested_select_does_not_map_to_outer_column() -> None:
    assert not analyze_parameters("select id from t where id=(select ?)")[0].columns


def test_ambiguous_comparison_and_unknown_projection_are_explicit() -> None:
    assert len(analyze_parameters("select id from t where a+b=?")[0].columns) == 2
    assert analyze_parameters("select ? from t")[0].reason


def test_positional_start_and_utf8_positions() -> None:
    query = 'select "Имя" from "Люди" where id=?'
    parameter = analyze_parameters(query, positional_start=3)[0]
    assert (
        parameter.position == 4
        and query[parameter.text_start : parameter.text_end] == "?"
    )


def test_tsql_named_parameter_and_mysql_marker() -> None:
    assert (
        analyze_parameters("select id from t where id=@id", "tsql")[0].parameter_name
        == "id"
    )
    assert (
        analyze_parameters("select `ID` from `Users` where `ID`=?", "mysql")[0]
        .columns[0]
        .column_name.quoted
    )


def test_invalid_profile_rejected() -> None:
    with pytest.raises(ValueError):
        analyze_parameters("select ?", "guess")
