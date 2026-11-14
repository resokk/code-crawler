import pytest

from code_crawler.query_benchmark import fixture_sources, plan_nodes


def test_workload_includes_calls_sql_and_duplicate_type_candidates():
    sources = fixture_sources(2)
    assert len(sources) == 6
    assert "PreparedStatement" in sources["Repo0.java"]
    assert "table_0" in sources["Repo0.java"]
    assert "next.run" in sources["Service0.java"]
    assert sources["copies/a/External.java"] == sources["copies/b/External.java"]
    with pytest.raises(ValueError):
        fixture_sources(0)


def test_plan_traversal_includes_nested_and_hashed_subplans():
    plan = {
        "Node Type": "Sort",
        "Plans": [
            {"Node Type": "Seq Scan", "Relation Name": "ucm_relations"},
            {
                "Node Type": "Index Scan",
                "Index Name": "candidate_idx",
                "Parent Relationship": "SubPlan",
            },
        ],
    }
    assert [p["Node Type"] for p in plan_nodes(plan)] == [
        "Sort",
        "Seq Scan",
        "Index Scan",
    ]
