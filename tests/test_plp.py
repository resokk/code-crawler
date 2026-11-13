from pathlib import Path

from code_crawler import indexer, plp

LIB = """
function SetRate(p_cred ref [PR_CRED], p_code varchar2) return ref [PRC_RATES] is
  r ref [PRC_RATES];
  n number;
begin
  select prc(prc.[PRC]) in ::[PRC_RATES], (::[TYPE_PRC_RATES] all : tprc) all
   where prc.[CREDIT] = p_cred and tprc.[CODE] = p_code into n;
  update x(x.[PRC] = n) in ::[PRC_RATES] all where x%id = r;
  delete d in ::[PRC_RATES] all where d.[CREDIT] = p_cred;
  for c in p_cred.[LIST_PAY] loop null; end loop;
  -- ::[PRC_RATES].[NEW_AUTO](p_cred);
  r := ::[PRC_RATES].[NEW_AUTO](P_CREDIT == p_cred, P_PRC == n);
  n := ::[OTHER].[LIB].Calc(1);
  return r;
end;

procedure SetRateFirst(p_cred ref [PR_CRED]) is
begin
  SetRate(p_cred, 'FIRST');
end;
"""


def test_parse_extracts_functions_queries_and_calls() -> None:
    unit = plp.parse(LIB)

    assert unit.syntax_errors == 0
    assert [f.name for f in unit.functions] == ["SETRATE", "SETRATEFIRST"]
    assert [(q.operation, q.classes) for q in unit.queries] == [
        ("select", {"PRC_RATES": {"read"}, "TYPE_PRC_RATES": {"read"}}),
        ("update", {"PRC_RATES": {"update"}}),
        ("delete", {"PRC_RATES": {"delete"}}),
    ]
    assert unit.queries[0].attributes == {
        ("PRC_RATES", "PRC"): {"select"},
        ("PRC_RATES", "CREDIT"): {"where"},
        ("TYPE_PRC_RATES", "CODE"): {"where"},
    }
    assert unit.queries[1].attributes == {("PRC_RATES", "PRC"): {"write"}}
    assert [(c.owner, c.target) for c in unit.calls] == [
        (0, ("PRC_RATES", "NEW_AUTO")),
        (0, ("OTHER", "LIB", "CALC")),
    ]
    assert (1, "SETRATE") in unit.local_names


def test_own_attribute_assignment_is_a_write() -> None:
    unit = plp.parse("begin [CREDIT] := P_CREDIT; x.[PRC] := 1; v := 2; end;")

    assert unit.own_writes == {"CREDIT"}


def test_index_links_callers_to_the_inserting_operation(tmp_path: Path) -> None:
    files = {
        "type/dictionary/prc_rates/methods/new_auto/src/execute.plp": (
            "begin [CREDIT] := P_CREDIT; end;"
        ),
        "type/dictionary/prc_rates/methods/lib/src/private.plp": LIB,
    }
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True)
        (tmp_path / path).write_text(text)

    graph = indexer.build(tmp_path, list(files), lambda: None)

    assert graph.failed == []
    name = {index: node[2] for index, node in enumerate(graph.nodes)}
    inserts = {
        name[node]
        for node, kind, table, column, attrs in graph.refs
        if table == "z#prc_rates" and column is None and attrs["access"] == "insert"
    }
    assert inserts == {"PRC_RATES.NEW_AUTO"}
    calls = {
        (name[src], name[dst]) for src, dst, kind, _ in graph.edges if kind == "calls"
    }
    assert calls == {
        ("PRC_RATES.LIB.SETRATE", "PRC_RATES.NEW_AUTO"),
        ("PRC_RATES.LIB.SETRATEFIRST", "PRC_RATES.LIB.SETRATE"),
    }
    assert ("uses", "z#prc_rates", "c_credit") in {
        (kind, table, column) for _, kind, table, column, _ in graph.refs
    }
