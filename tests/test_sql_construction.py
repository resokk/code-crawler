import asyncio
import hashlib
from uuid import UUID

import pytest
from pydantic import ValidationError

from code_crawler.incremental import SourceInput
from code_crawler.ingestion import UcmBatch
from code_crawler.java_sql import JavaSqlAnalyzer
from code_crawler.ucm import (
    EntityType,
    Relation,
    SourceFile,
    SqlConstruction,
    SqlFragment,
    SqlVariant,
    Symbol,
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
    captured = SourceInput(file, content)
    analyses = asyncio.run(JavaSqlAnalyzer((captured,))((captured,)))
    batch = UcmBatch(repository_id=REPO, entities=(file, *analyses[0].entities))
    assert UcmBatch.model_validate_json(batch.model_dump_json()) == batch
    return batch


def constructions(batch: UcmBatch, owner: str | None = None) -> list[SqlConstruction]:
    symbols = {e.id: e for e in batch.entities if isinstance(e, Symbol)}
    return [
        e
        for e in batch.entities
        if isinstance(e, SqlConstruction)
        and (owner is None or symbols[e.owner_symbol_id].qualified_name == owner)
    ]


def texts(batch: UcmBatch, owner: str | None = None) -> set[str]:
    return {v.text for c in constructions(batch, owner) for v in c.variants}


def test_unused_sql_is_candidate_not_execution() -> None:
    batch = analyze('class A { void m(){ String sql="delete from users"; } }')
    assert texts(batch, "A.m") == {"delete from users"}
    assert all(
        not e.relation_kind.value.startswith("EXECUTES")
        for e in batch.entities
        if isinstance(e, Relation)
    )
    assert all(c.source_range is not None for c in constructions(batch))


def test_constants_and_qualified_references_do_not_leak_between_classes() -> None:
    batch = analyze("""class A { static final String TABLE="users"; void m(){ use("select id from "+TABLE); use("select id from "+B.TABLE); } }
        class B { static final String TABLE="orders"; void m(){ use("select id from "+TABLE); } }""")
    assert {"select id from users", "select id from orders"} <= texts(batch, "A.m")
    assert "select id from orders" in texts(batch, "B.m")
    assert "select id from users" not in texts(batch, "B.m")


def test_parameter_local_shadowing_and_this_field() -> None:
    batch = analyze("""class A { final String TABLE="users"; void m(String TABLE){
        use("select id from "+TABLE); use("select id from "+this.TABLE);
    } void n(){ { String TABLE="orders"; use("select id from "+TABLE); } use("select id from "+TABLE); } }""")
    assert {"select id from __unknown__", "select id from users"} <= texts(batch, "A.m")
    assert {"select id from orders", "select id from users"} <= texts(batch, "A.n")


def test_nonfinal_and_external_fields_remain_dynamic() -> None:
    batch = analyze(
        'class A { String TABLE="users"; void m(){ use("select id from "+TABLE); use("select id from "+External.TABLE); } }'
    )
    assert "select id from users" not in texts(batch, "A.m")
    assert "select id from __unknown__" in texts(batch, "A.m")


def test_dynamic_fragment_origin_and_static_placeholder_are_distinct() -> None:
    batch = analyze(
        'class A { void m(String p){ use("select id from t where name="+p); use("select id from __unknown__"); } }'
    )
    variants = [v for c in constructions(batch) for v in c.variants]
    dynamic = next(
        v for v in variants if v.text == "select id from t where name=__unknown__"
    )
    assert dynamic.partial and dynamic.partial_reasons
    assert any(
        f.kind == "DYNAMIC" and f.source_range is not None for f in dynamic.fragments
    )
    literal = next(v for v in variants if v.text == "select id from __unknown__")
    assert not literal.partial and all(f.kind == "STATIC" for f in literal.fragments)


def test_if_and_ternary_variants_are_not_concatenated_together() -> None:
    batch = analyze("""class A { void m(boolean f){ String q;
        if(f) q="select id from a"; else q="select id from b"; use(q);
        String t=f?"delete from c":"delete from d"; use(t);
    } }""")
    assert any(
        {v.text for v in c.variants} == {"select id from a", "select id from b"}
        for c in constructions(batch)
    )
    assert any(
        {v.text for v in c.variants} == {"delete from c", "delete from d"}
        for c in constructions(batch)
    )


def test_builder_optional_append_yields_distinct_paths() -> None:
    batch = analyze("""class A { void m(boolean f){ StringBuilder b=new StringBuilder("select id from t");
        if(f) b.append(" where id=1"); use(b.toString()); } }""")
    assert {"select id from t", "select id from t where id=1"} <= texts(batch)


def test_join_format_textblock_and_reassignment() -> None:
    batch = analyze('''class A { void m(String p){
        use(String.join(" ","select id","from t"));
        use(String.format("select %s from t where id=%d",p,1));
        String q="delete from old"; q="delete from fresh";
        use("""\n            select id\n            from blocks\n            """);
    } }''')
    assert {
        "select id from t",
        "select __unknown__ from t where id=1",
        "delete from old",
        "delete from fresh",
        "select id\nfrom blocks",
    } <= texts(batch)


def test_jpql_is_not_relabelled_as_native_sql() -> None:
    batch = analyze("""interface A {
        @Query("select u from User u") Object jpql();
        @Query(value="select id from native_table",nativeQuery=true) Object nativeSql();
    }""")
    assert "select u from User u" not in texts(batch)
    assert "select id from native_table" in texts(batch)


def test_sql_literal_inside_non_sql_expression_is_still_discovered() -> None:
    batch = analyze('class A { void m(){ log("message: "+"select id from t"); } }')
    assert "select id from t" in texts(batch)


def test_loop_and_builder_alias_are_not_complete_values() -> None:
    loop = analyze(
        'class A { void m(boolean f){ String q="select id from t"; while(f){ q+=" where x=1"; } use(q); } }'
    )
    assert any(
        v.partial and "loop repetition is bounded" in v.partial_reasons
        for c in constructions(loop)
        for v in c.variants
    )
    alias = analyze(
        'class A { void m(){ StringBuilder b=new StringBuilder("select id from t"); StringBuilder a=b; a.append(" where x=1"); use(b.toString()); } }'
    )
    assert any(
        v.partial and any("alias" in r for r in v.partial_reasons)
        for c in constructions(alias)
        for v in c.variants
    )


def test_path_limit_is_explicit() -> None:
    branches = "".join('if(f) q+=" x"; else q+=" y";' for _ in range(6))
    with pytest.raises(ValueError, match="path limit"):
        analyze(
            'class A { void m(boolean f){ String q="select id from t";'
            + branches
            + "use(q); } }"
        )


@pytest.mark.parametrize(
    "fields",
    [
        {
            "text": "different",
            "partial": False,
            "fragments": (SqlFragment(kind="STATIC", text="select id from t"),),
        },
        {
            "text": "select id from t",
            "partial": True,
            "fragments": (SqlFragment(kind="STATIC", text="select id from t"),),
        },
        {
            "text": "select id from t",
            "partial": False,
            "fragments": (SqlFragment(kind="DYNAMIC", text="select id from t"),),
        },
    ],
)
def test_variant_invariants_reject_inconsistent_payload(fields: dict) -> None:
    with pytest.raises(ValidationError):
        SqlVariant(
            candidate_id=logical_id(str(REPO), EntityType.SQL_CANDIDATE, "candidate"),
            **fields,
        )


def test_numeric_addition_is_not_misread_as_string_concatenation() -> None:
    batch = analyze('class A { void m(){ use("select id from t where id="+(1+2)); } }')
    assert "select id from t where id=12" not in texts(batch)
    variant = next(
        v
        for c in constructions(batch)
        for v in c.variants
        if v.text == "select id from t where id=__unknown__"
    )
    assert variant.partial


def test_dynamic_format_template_keeps_dynamic_fragment_flags() -> None:
    batch = analyze(
        'class A { void m(String column,int id){ String f="select "+column+" from t where id=%d"; use(String.format(f,id)); } }'
    )
    variant = next(
        v
        for c in constructions(batch)
        for v in c.variants
        if v.text == "select __unknown__ from t where id=__unknown__"
    )
    assert sum(f.kind == "DYNAMIC" for f in variant.fragments) == 2


def test_unknown_builder_mutation_is_partial() -> None:
    batch = analyze(
        'class A { void m(){ StringBuilder b=new StringBuilder("select id from t"); b.reverse(); use(b.toString()); } }'
    )
    assert any(
        v.partial and "unsupported builder mutation" in v.partial_reasons
        for c in constructions(batch)
        for v in c.variants
    )


def test_final_mutable_builder_field_is_not_folded_as_immutable_string() -> None:
    batch = analyze(
        'class A { static final StringBuilder SQL=new StringBuilder("select id from t"); void m(){ use(SQL.toString()); } }'
    )
    assert "select id from t" not in texts(batch, "A.m")
    assert "select id from t" in texts(batch, "A")


def test_jpql_calls_and_commented_native_flag_are_not_sql_candidates() -> None:
    batch = analyze("""interface A {
        @Query(value="select u from User u", nativeQuery=false /* nativeQuery=true */) Object m();
        default void n(){ em.createQuery("select e from Entity e"); em.createNamedQuery("select x from X x"); }
    }""")
    assert "select u from User u" not in texts(batch)
    assert "select e from Entity e" not in texts(batch)
    assert "select x from X x" not in texts(batch)


def test_integer_string_conversion_and_invalid_format_type_are_not_confused() -> None:
    batch = analyze(
        'class A { void m(){ use("select id from t where id="+1_000L); use(String.format("select id from t where id=%d","x")); use("select id from t where x="+1.0f); } }'
    )
    assert "select id from t where id=1000" in texts(batch)
    bad = next(
        v
        for c in constructions(batch)
        for v in c.variants
        if v.text == "select id from t where id=x"
    )
    assert bad.partial and "unsupported format argument type" in bad.partial_reasons
    assert "select id from t where x=1.0f" not in texts(batch)


def test_java_unicode_and_character_escape_origins_are_recovered() -> None:
    batch = analyze(
        r"""class A { void m(){ use("select id from \u0074"); use("select id from t"+'\n'+"where id=1"); } }"""
    )
    assert "select id from t" in texts(batch)
    assert "select id from t\nwhere id=1" in texts(batch)


def test_nested_type_constant_aliases_follow_lexical_owner() -> None:
    batch = analyze("""class A { static class B { static final String TABLE="a"; } void m(){ use("select id from "+B.TABLE); } }
        class C { static class B { static final String TABLE="c"; } void m(){ use("select id from "+B.TABLE); } }""")
    assert "select id from a" in texts(batch, "A.m")
    assert "select id from c" not in texts(batch, "A.m")
    assert "select id from c" in texts(batch, "C.m")


def test_field_receiver_shadows_same_named_type_constant() -> None:
    batch = analyze("""class B { static final String TABLE="wrong"; }
        class A { Object B; void m(){ use("select id from "+B.TABLE); } }""")
    assert "select id from wrong" not in texts(batch, "A.m")
    assert "select id from __unknown__" in texts(batch, "A.m")


def test_this_does_not_resolve_an_enclosing_class_field() -> None:
    batch = analyze(
        """class A { final String TABLE="outer"; class B { void m(){ use("select id from "+this.TABLE); use("select id from "+TABLE); } } }"""
    )
    assert "select id from __unknown__" in texts(batch, "A.B.m")
    assert "select id from outer" in texts(batch, "A.B.m")
