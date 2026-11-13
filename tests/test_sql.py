from code_crawler.sql import analyze, looks_like_sql


def test_select_with_join_resolves_tables_columns_and_lineage() -> None:
    result = analyze(
        "select u.id, o.total + o.tax as amount from users u "
        "left join orders o on o.user_id = u.id where u.status = :st and o.created > ?1"
    )

    assert result.operation == "select"
    assert result.tables == {"users": {"read"}, "orders": {"read"}}
    assert result.columns[("users", "id")] == {"select", "join"}
    assert result.columns[("users", "status")] == {"where"}
    assert result.joins == [
        {"type": "left", "table": "orders", "on": "o.user_id = u.id"}
    ]
    assert result.conditions == ["u.status = :st AND o.created > ?"]
    assert result.lineage == {
        "id": ["users.id"],
        "amount": ["orders.tax", "orders.total"],
    }


def test_lineage_goes_through_cte_and_derived_table() -> None:
    result = analyze(
        "with c as (select a from t1) "
        "select c.a, q.k from c join (select k from t2) q on true"
    )

    assert result.tables == {"t1": {"read"}, "t2": {"read"}}
    assert result.lineage == {"a": ["t1.a"], "k": ["t2.k"]}


def test_writes_are_attributed_to_target_table() -> None:
    insert = analyze("insert into t (a, b) select x, y from s")
    update = analyze("update t set a = s.a from s where t.id = s.id")

    assert insert.tables == {"t": {"insert"}, "s": {"read"}}
    assert insert.columns[("t", "a")] == {"write"}
    assert insert.lineage == {"a": ["s.x"], "b": ["s.y"]}
    assert update.tables == {"t": {"update"}, "s": {"read"}}
    assert update.columns[("t", "a")] == {"write"}
    assert update.columns[("s", "a")] == {"select"}


def test_unqualified_column_with_several_sources_stays_unresolved() -> None:
    result = analyze("select name from a join b on a.id = b.id")

    assert result.unresolved_columns == {"name"}
    assert result.lineage == {"name": []}


def test_placeholder_is_not_reported_as_table_or_column() -> None:
    result = analyze("select a from t where b = __unknown__ and c in (__unknown__)")

    assert result.tables == {"t": {"read"}}
    assert set(result.columns) == {("t", "a"), ("t", "b"), ("t", "c")}


def test_unparseable_text_is_reported_as_not_parsed() -> None:
    assert analyze("delete from cache now please").parsed is False


def test_looks_like_sql_rejects_ordinary_messages() -> None:
    assert looks_like_sql("  SELECT a\nFROM t")
    assert looks_like_sql("update t set a = 1")
    assert not looks_like_sql("Update failed for user")
    assert not looks_like_sql("select an option")
