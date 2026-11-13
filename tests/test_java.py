from code_crawler import java


def queries(body: str, members: str = "") -> list[tuple[str, bool]]:
    source = (
        f"package p; class C {{ {members} void m(String p, boolean f) {{ {body} }} }}"
    )
    symbols = java.parse(source.encode())
    return [(q.text, q.partial) for q in symbols[-1].queries]


def test_symbols_are_nested_with_qualified_names() -> None:
    symbols = java.parse(
        b"package a.b; class Outer { void m() {} interface In { void n(); } }"
    )

    assert [(s.kind, s.qualified_name, s.parent) for s in symbols] == [
        ("class", "a.b.Outer", None),
        ("method", "a.b.Outer.m", 0),
        ("class", "a.b.Outer.In", 0),
        ("method", "a.b.Outer.In.n", 2),
    ]
    assert symbols[2].attrs == {"type": "interface"}


def test_concatenation_with_constants_and_reassignment() -> None:
    body = """
        String sql = "select a from " + TABLE;
        sql += " where id = ?";
        sql = sql + " order by a";
        run(sql);
    """
    assert queries(body, 'static final String TABLE = "t";') == [
        ("select a from t where id = ? order by a", False)
    ]


def test_string_builder_chain_with_unknown_and_conditional_parts() -> None:
    body = """
        StringBuilder sb = new StringBuilder("select a ");
        sb.append("from t").append(" where p = ").append(p);
        if (f) { sb.append(" and x = 1"); }
        if (sb.length() > 0) { log(sb.length()); }
        run(sb.toString());
    """
    assert queries(body) == [("select a from t where p = __unknown__ and x = 1", True)]


def test_join_format_and_text_block() -> None:
    body = '''
        run(String.join(" ", "delete from", "t", "where id = ?"));
        run(String.format("select %s from %s where n = %d", p, "t", 5));
        run("update t set a = 1 where b = %s".formatted(p));
        run("""
            select x
            from y""");
    '''
    assert queries(body) == [
        ("delete from t where id = ?", False),
        ("select __unknown__ from t where n = 5", True),
        ("update t set a = 1 where b = __unknown__", True),
        ("select x\nfrom y", False),
    ]


def test_each_branch_value_is_a_separate_query() -> None:
    body = """
        String sql;
        if (f) sql = "select 1 from a"; else sql = "select 2 from b";
        run(sql);
        run(f ? "select 3 from c" : "select 4 from d");
    """
    assert [text for text, _ in queries(body)] == [
        "select 1 from a",
        "select 2 from b",
        "select 3 from c",
        "select 4 from d",
    ]


def test_native_query_annotation_is_sql_and_jpql_is_not() -> None:
    symbols = java.parse(
        b"""interface R {
            @Query(value = "select * from t where a = ?1", nativeQuery = true) X a();
            @Query("select u from User u") X b();
            default X c() { return em.createQuery("select u from User u"); }
        }"""
    )

    assert [[q.text for q in s.queries] for s in symbols] == [
        [],
        ["select * from t where a = ?1"],
        [],
        [],
    ]


def test_ordinary_strings_are_not_queries() -> None:
    assert queries('log.info("Update failed for user " + p); String s = "hello";') == []
