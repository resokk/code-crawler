import argparse
import asyncio
import json
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import pytest
from test_java_calls import source

from code_crawler import cli, sql_paths
from code_crawler.java_database import JavaDatabaseAnalyzer
from code_crawler.java_execution import JavaExecutionAnalyzer
from code_crawler.java_lineage import JavaLineageAnalyzer
from code_crawler.java_orm import JavaOrmAnalyzer
from code_crawler.java_semantic import JavaSemanticAnalyzer
from code_crawler.java_sql import JavaSqlAnalyzer
from code_crawler.sql_paths import PathLimitCase, SqlPathOptions
from code_crawler.ucm import SqlConstruction


def code(branches=3, sql=False):
    flags = ",".join(f"boolean f{i}" for i in range(branches))
    body = 'String q="select id from t";' if sql else "int n=0;"
    body += "".join(
        f"if(f{i}){{"
        + ('q+=" x";' if sql else "n++;")
        + "}else{"
        + ('q+=" y";' if sql else "n--;")
        + "}"
        for i in range(branches)
    )
    return f"class A {{ void m({flags}){{{body}}} }}"


def analyze(text, budget, callback=None, analyzer_class=JavaSqlAnalyzer):
    captured = source("A.java", text)
    extra = (
        {"schemas": (), "assignments": ()}
        if analyzer_class is JavaDatabaseAnalyzer
        else {}
    )
    analyzer = analyzer_class(
        (captured,), sql_options=SqlPathOptions(budget, callback), **extra
    )
    result = asyncio.run(analyzer((captured,)))
    return analyzer, result[0]


@pytest.mark.parametrize("value", [0, -1, True, False, 1.5, "256", 65537, None])
def test_invalid_budget_is_rejected(value):
    with pytest.raises(ValueError, match="1..65536"):
        SqlPathOptions(value)


@pytest.mark.parametrize(
    "budget,branches,overflow",
    [
        (256, 8, False),
        (256, 9, True),
        (1, 0, False),
        (1, 1, True),
        (5, 3, True),
        (8, 3, False),
    ],
)
def test_exact_boundary_and_overflow_without_any_sql(budget, branches, overflow):
    observations = []
    _, result = analyze(code(branches), budget, observations.append)
    assert len(observations) == 1
    assert not any(isinstance(e, SqlConstruction) for e in result.entities)
    case = observations[0]
    assert (case is not None) == overflow
    if case:
        assert case.path == "A.java" and case.qualified_name == "A.m"
        assert case.max_paths == budget and case.retained_paths <= budget
        assert case.attempted_paths_lower_bound > budget and case.pruning_events > 0
        assert case.start_byte < case.end_byte
        assert (
            case.content_sha256 == source("A.java", code(branches)).file.content_sha256
        )
        assert not {"sql", "source", "body", "message"} & asdict(case).keys()


def test_budget_identity_is_independent_of_report_and_concurrent_analyzers():
    text = code(4, True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        low = pool.submit(analyze, text, 2)
        high = pool.submit(analyze, text, 16)
        low_analyzer, low_result = low.result()
        high_analyzer, high_result = high.result()
    assert low_analyzer.analysis_version != high_analyzer.analysis_version
    observed = []
    reported, reported_result = analyze(text, 2, observed.append)
    assert reported.analysis_version == low_analyzer.analysis_version
    assert reported_result == low_result
    low_variants = [
        v
        for e in low_result.entities
        if isinstance(e, SqlConstruction)
        for v in e.variants
        if v.text.startswith("select id from t ")
    ]
    high_variants = [
        v
        for e in high_result.entities
        if isinstance(e, SqlConstruction)
        for v in e.variants
        if v.text.startswith("select id from t ")
    ]
    assert len(low_variants) == 2 and len(high_variants) == 16
    assert all(
        "path limit reached: variants truncated" in v.partial_reasons
        for v in low_variants
    )
    assert all(
        "path limit reached: variants truncated" not in v.partial_reasons
        for v in high_variants
    )


@pytest.mark.parametrize(
    "profile",
    [
        JavaSqlAnalyzer,
        JavaExecutionAnalyzer,
        JavaSemanticAnalyzer,
        JavaLineageAnalyzer,
        JavaDatabaseAnalyzer,
        JavaOrmAnalyzer,
    ],
)
def test_derived_profiles_report_once_and_honor_budget(profile):
    observed = []
    analyzer, _ = analyze(code(3), 2, observed.append, profile)
    assert analyzer.sql_options.max_paths == 2
    assert len(observed) == 1 and observed[0].retained_paths == 2


def example():
    return PathLimitCase(
        "repo", "A.java", "a" * 64, "owner", "A.m", "METHOD", 1, 2, 0, 20, 2, 4, 1, 2
    )


def test_report_private_atomic_and_metadata_only(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = tmp_path / "paths.jsonl"
    target.write_text("previous report")
    report = sql_paths.PathReport(target, root, "repo", 2)
    report.record(None)
    report.record(example())
    assert target.read_text() == "previous report"
    report.finish("ANALYZED", {"reused_files": 3})
    report.record(example())  # sealed: late worker callbacks cannot corrupt it
    report.close()
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert rows[0]["analyzed_methods"] == 2 and rows[0]["overflow_cases"] == 1
    assert (
        rows[0]["scope"] == "reanalyzed_methods_only" and rows[0]["reused_files"] == 3
    )
    assert len(rows) == 2 and rows[1]["record"] == "case"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".sql-paths-*"))


def test_failed_report_export_keeps_old_file_and_preserves_original_error(
    tmp_path, monkeypatch
):
    root = tmp_path / "repo"
    root.mkdir()
    target = tmp_path / "paths.jsonl"
    target.write_text("old")

    def fail(*args):
        raise OSError("replace failed")

    monkeypatch.setattr(sql_paths.os, "replace", fail)

    async def run():
        async with sql_paths.reporting(str(target), root, "repo", 2) as report:
            report.record(example())
            raise LookupError("original analysis failure")

    with pytest.raises(LookupError, match="original analysis failure") as caught:
        asyncio.run(run())
    assert "SQL path report export failed" in caught.value.__notes__[0]
    assert target.read_text() == "old" and not list(tmp_path.glob(".sql-paths-*"))


def test_cancelled_context_exports_failed_and_closes(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    target = tmp_path / "paths.jsonl"
    stored = []

    async def run():
        started = asyncio.Event()

        async def worker():
            async with sql_paths.reporting(str(target), root, "repo", 2) as report:
                stored.append(report)
                report.record(example())
                started.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(worker())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert json.loads(target.read_text().splitlines()[0])["status"] == "FAILED"
    assert stored[0]._stream.closed


def test_report_preflight_and_cli_validation(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(ValueError, match="outside"):
        sql_paths.PathReport(root / "paths.jsonl", root, "repo", 2)
    with pytest.raises(FileNotFoundError):
        sql_paths.PathReport(tmp_path / "missing" / "paths.jsonl", root, "repo", 2)
    assert cli._sql_max_paths("256") == 256
    for value in ("0", "-1", "1.2", "65537", "abc"):
        with pytest.raises(
            argparse.ArgumentTypeError, match="1..65536|invalid literal"
        ):
            cli._sql_max_paths(value)
