"""Differential facts and direct write-barrier regressions, not a literal heuristic."""

import copy

import pytest
from test_sql_construction import analyze

from code_crawler import java, java_sql


def eager_clone(flow):
    result = copy.copy(flow)
    result.variables, result.frames = copy.deepcopy((flow.variables, flow.frames))
    result.choices = dict(flow.choices)
    result.queries = list(flow.queries)
    result.reads = set()
    result._shared = False
    return result


CASES = [
    "String q=BASE; if(f){q+=FILTER;}else{q=OTHER;} use(q);",
    "String q=BASE; if(f){q=p;}else{q+=p;} use(q);",
    "String q=BASE; if(f){String q2=q; use(q2);} use(q);",
    "String q=BASE; if(f){String q=OTHER; if(f){q+=FILTER;}use(q);}use(q);",
    "StringBuilder b=new StringBuilder(BASE); StringBuilder a=b; if(f){a.append(FILTER);}else{b.setLength(0);}use(b.toString());",
    "StringBuilder b=new StringBuilder(BASE); if(f){use(b.append(FILTER).toString());}else{b.reverse();}use(b.toString());",
    "StringBuilder b=new StringBuilder(BASE); if(f){b.insert(0,p);}use(b.toString());",
    "String q=BASE; if(f){use(q);}else{q=OTHER;} q+=FILTER;use(q);",
    "String q=BASE; while(f){q+=FILTER;}use(q);",
    "String q=BASE; q=f?q+FILTER:OTHER; use(q);",
    "String q=BASE;" + "if(f){touch();}else{touch();}" * 6 + "use(q);",
    "String q=BASE;" + "if(f){q+=FILTER;}else{q+=OTHER;}" * 6 + "use(q);",
]


@pytest.mark.parametrize("body", CASES)
@pytest.mark.parametrize("limit", [5, 1024])
def test_full_fact_payload_matches_eager_clone(monkeypatch, body, limit):
    source = """class A {
      static final String BASE="select id from users", FILTER=" where id=1", OTHER="delete from users";
      void m(boolean f,String p) { BODY }
    }""".replace("BODY", body)
    monkeypatch.setattr(java_sql, "_MAX_PATHS", limit)
    lazy = analyze(source)
    monkeypatch.setattr(java_sql._SqlFlow, "clone", eager_clone)
    eager = analyze(source)
    assert lazy.model_dump_json() == eager.model_dump_json()


def test_clone_shares_until_write_and_preserves_nested_aliases(monkeypatch):
    parsed = java.analyze(b"class A {}")
    flow = java_sql._SqlFlow({}, java._span(parsed._tree.root_node))
    value = java._Value("select id from users")
    variable = java._Variable(value, 0, True, 1)
    saved = java._Variable(value, 0, False, 1)
    flow.variables = {"a": variable, "b": variable}
    flow.frames = [{"shadow": saved}]
    calls = []
    copy_state = java_sql._copy_state

    def counted(variables, frames):
        calls.append(1)
        return copy_state(variables, frames)

    monkeypatch.setattr(java_sql, "_copy_state", counted)
    child = flow.clone()
    sibling = flow.clone()
    assert not calls and child.variables is flow.variables
    child._writable()
    assert len(calls) == 1
    assert child.variables["a"] is child.variables["b"]
    assert child.variables["a"].value is child.frames[0]["shadow"].value
    child.variables["a"].value.partial = True
    assert not sibling.variables["a"].value.partial
    assert not flow.variables["a"].value.partial
    child._writable()
    assert len(calls) == 1
    flow._writable()
    assert len(calls) == 2
    flow.variables["a"].dirty = False
    assert sibling.variables["a"].dirty


def test_scope_exit_needs_no_value_copy_but_future_writes_stay_isolated(monkeypatch):
    parsed = java.analyze(b"class A {}")
    flow = java_sql._SqlFlow({}, java._span(parsed._tree.root_node))
    outer = java._Variable(java._Value("select id from outer_table"), 0, False, 1)
    flow.variables = {
        "q": java._Variable(java._Value("select id from inner_table"), 0, False, 1)
    }
    flow.frames = [{"q": outer}]
    child = flow.clone()
    sibling = flow.clone()
    child.pop()
    assert child.variables["q"] is outer
    assert sibling.variables["q"] is flow.variables["q"]
    child._writable()
    child.variables["q"].value.partial = True
    assert not outer.value.partial


def test_read_only_forks_share_bindings_without_materializing_values():
    flow = java_sql._SqlFlow({}, None)
    flow.variables["q"] = java._Variable(
        java._Value("select id from users"), 0, False, 1
    )
    first = flow.clone()
    second = flow.clone()
    assert first.variables is second.variables is flow.variables
    first.push()
    first.pop()
    assert first.variables is flow.variables


@pytest.mark.parametrize(
    "body",
    [
        "String q=BASE; if(f){q+=FILTER;}else{q=p;} s.executeQuery(q);",
        "StringBuilder b=new StringBuilder(BASE); if(f){s.executeQuery(b.append(FILTER).toString());}else{s.executeQuery(b.toString());}",
        "StringBuilder b=new StringBuilder(BASE); String q=BASE; q=unknown(s.executeQuery(b.append(FILTER).toString())); s.executeQuery(q);",
        "String q=BASE; if(f){java.sql.PreparedStatement ps=c.prepareStatement(q);ps.execute();}else{s.executeQuery(q);}",
    ],
)
def test_execution_preview_and_sink_facts_match_eager(monkeypatch, body):
    from test_java_execution import analyze as execute

    source = """import java.sql.*; class A {
      static final String BASE="select id from users",FILTER=" where id=1";
      String unknown(Object value){return "";}
      void m(boolean f,String p,Statement s,Connection c) throws Exception { BODY }
    }""".replace("BODY", body)
    lazy = execute(source)
    monkeypatch.setattr(java_sql._SqlFlow, "clone", eager_clone)
    assert lazy.model_dump_json() == execute(source).model_dump_json()
