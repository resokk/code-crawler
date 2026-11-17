"""Fixed cached/direct-decoding Java benchmark; run with python -m."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from code_crawler import java, java_calls, java_symbols
from code_crawler.incremental import SourceInput
from code_crawler.java_orm import JavaOrmAnalyzer
from code_crawler.java_sql_flow_benchmark import fixture as branch_fixture
from code_crawler.ucm import EntityType, SourceFile, logical_id

REPOSITORY = UUID("11111111-1111-1111-1111-111111111111")


def sources(case: str) -> tuple[SourceInput, ...]:
    contents = (
        [
            f"class Small{i} {{ int value; int get(){{return value;}} }}".encode()
            for i in range(24)
        ]
        if case == "small"
        else [
            branch_fixture("read_heavy").replace(
                b"class A ", f"class Paths{i} ".encode()
            )
            for i in range(4)
        ]
    )
    result = []
    for i, content in enumerate(contents):
        path = f"C{i}.java"
        file = SourceFile(
            repository_id=str(REPOSITORY),
            logical_key=path,
            name=path,
            path=path,
            language="java",
            id=logical_id(str(REPOSITORY), EntityType.SOURCE_FILE, path),
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        result.append(SourceInput(file, content))
    return tuple(result)


def worker(mode: str, case: str) -> dict:
    stats = {
        "calls": 0,
        "hits": 0,
        "misses": 0,
        "admitted": 0,
        "scopes": 0,
        "peak_text_bytes": 0,
    }
    original_scope, original_text = java._text_scope, java._text

    @contextmanager
    def traced():
        with original_scope() as cache:
            try:
                yield cache
            finally:
                for key in ("hits", "misses", "admitted"):
                    stats[key] += getattr(cache, key)
                stats["scopes"] += 1
                stats["peak_text_bytes"] = max(
                    stats["peak_text_bytes"], cache.peak_bytes
                )

    def text(node):
        stats["calls"] += int(node is not None)
        if mode == "off":
            return (
                node.text.decode("utf-8", errors="replace") if node is not None else ""
            )
        return original_text(node)

    if mode == "off":
        # Restore the pre-cache synchronous entry points as well as direct decoding.
        java.analyze = java.analyze.__wrapped__
        java_symbols.extract = java_symbols.extract.__wrapped__
        java_calls.extract = java_symbols.extract
        for cls in JavaOrmAnalyzer.__mro__:
            method = cls.__dict__.get("analysis")
            if method is not None and hasattr(method, "__wrapped__"):
                cls.analysis = method.__wrapped__

    java._text_scope = traced
    java._text = text
    captured = sources(case)

    async def run():
        analyzer = JavaOrmAnalyzer(captured)
        return await analyzer(captured)

    before = resource.getrusage(resource.RUSAGE_SELF)
    started = time.perf_counter()
    analyses = asyncio.run(run())
    seconds = time.perf_counter() - started
    after = resource.getrusage(resource.RUSAGE_SELF)
    entities = sorted(
        entity.model_dump_json()
        for analysis in analyses
        for entity in analysis.entities
    )
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
        1 if sys.platform == "darwin" else 1024
    )
    return {
        "mode": mode,
        "case": case,
        "files": len(captured),
        "seconds": seconds,
        "peak_rss_bytes": peak,
        "entities": len(entities),
        "facts_sha256": hashlib.sha256(json.dumps(entities).encode()).hexdigest(),
        "fixture_sha256": hashlib.sha256(
            b"\0".join(s.content for s in captured)
        ).hexdigest(),
        "decoded_calls": stats["calls"] - stats["hits"],
        "analysis_io_in_blocks": after.ru_inblock - before.ru_inblock,
        "analysis_io_out_blocks": after.ru_oublock - before.ru_oublock,
        **stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("off", "on"))
    parser.add_argument("--case", choices=("small", "sql_paths"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        if args.case is None:
            parser.error("--worker requires --case")
        print(json.dumps(worker(args.worker, args.case)))
        return
    results = []
    for case in ("small", "sql_paths"):
        for sample in range(3):
            for mode in ("off", "on") if sample % 2 == 0 else ("on", "off"):
                output = subprocess.check_output(
                    [
                        sys.executable,
                        "-m",
                        "code_crawler.java_text_benchmark",
                        "--worker",
                        mode,
                        "--case",
                        case,
                    ],
                    text=True,
                )
                results.append({**json.loads(output), "sample": sample})
    summary = []
    for case in ("small", "sql_paths"):
        for mode in ("off", "on"):
            rows = [
                row for row in results if row["case"] == case and row["mode"] == mode
            ]
            summary.append(
                {
                    "case": case,
                    "mode": mode,
                    "median_seconds": statistics.median(row["seconds"] for row in rows),
                    "median_peak_rss_bytes": statistics.median(
                        row["peak_rss_bytes"] for row in rows
                    ),
                }
            )
    root = Path(__file__).parent
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "physical_memory_bytes": os.sysconf("SC_PHYS_PAGES")
        * os.sysconf("SC_PAGE_SIZE"),
        "cgroup": {
            name: Path("/sys/fs/cgroup", name).read_text().strip()
            for name in ("cpu.max", "memory.max")
            if Path("/sys/fs/cgroup", name).exists()
        },
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("tree-sitter", "tree-sitter-java", "sqlglot")
        },
        "source_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                root / name
                for name in (
                    "java.py",
                    "java_symbols.py",
                    "java_calls.py",
                    "java_sql.py",
                    "java_execution.py",
                    "java_semantic.py",
                    "java_lineage.py",
                    "java_database.py",
                    "java_orm.py",
                    "java_text_benchmark.py",
                    "java_sql_flow_benchmark.py",
                )
            )
        },
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "uv_lock_sha256": hashlib.sha256(
            root.parents[1].joinpath("uv.lock").read_bytes()
        ).hexdigest(),
        "summary": summary,
        "results": results,
        "equivalent": all(
            len({row["facts_sha256"] for row in results if row["case"] == case}) == 1
            for case in ("small", "sql_paths")
        ),
        "limits": {
            "entries": java._TEXT_MAX_ENTRIES,
            "text_bytes": java._TEXT_MAX_BYTES,
        },
        "limitations": "Three fresh processes per mode/case, alternating order; numeric instrumentation is included in timing. Same ORM pipeline with direct or cached text decoding. RSS includes imports/fact serialization; timing covers construction and analysis. Synthetic evidence, not a production SLA.",
    }
    content = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(content)
    else:
        print(content)
    if not report["equivalent"]:
        raise SystemExit("fact mismatch")


if __name__ == "__main__":
    main()
