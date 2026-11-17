"""Opt-in fixed-corpus benchmark: python -m code_crawler.java_sql_flow_benchmark."""

import argparse
import ast
import asyncio
import copy
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

from code_crawler import java, java_sql
from code_crawler.incremental import SourceInput
from code_crawler.ucm import EntityType, SourceFile, logical_id

BASELINE = "d07a14d193e3c0db907a2223cd35a45c263baa51"
REPOSITORY = UUID("11111111-1111-1111-1111-111111111111")


def fixture(kind: str) -> bytes:
    count = 128 if kind == "read_heavy" else 32
    declarations = "".join(f'String v{i}="value{i}";' for i in range(count))
    branch = (
        "if(f){touch();}else{touch();}"
        if kind == "read_heavy"
        else "if(f){q+=TAIL;}else{q+=OTHER;}"
    )
    body = (
        declarations
        + "String q=BASE;use(q);"
        + branch * (18 if kind == "read_heavy" else 10)
        + "use(q);"
    )
    return (
        'class A { static final String BASE="select id from users",TAIL=" where id=1",OTHER=" order by id"; void m(boolean f){'
        + body
        + "} }"
    ).encode()


def baseline_clone():
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:src/code_crawler/java_sql.py"], text=True
    )
    tree = ast.parse(source)
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "_SqlFlow"
    )
    method = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "clone"
    )
    namespace = {"copy": copy, "java": java}
    # Fixed repository commit; never accepts external source or a user-selected revision.
    exec(  # noqa: S102 - trusted fixed-commit baseline only
        compile(ast.Module(body=[method], type_ignores=[]), "<baseline-clone>", "exec"),
        namespace,
    )
    return namespace["clone"]


def deepcopy_clone(flow):
    result = copy.copy(flow)
    result.variables, result.frames = copy.deepcopy((flow.variables, flow.frames))
    result.choices = dict(flow.choices)
    result.queries = list(flow.queries)
    result.reads = set()
    result._shared = False
    return result


def worker(mode: str, kind: str) -> dict:
    counters = {"clones": 0, "materializations": 0}
    selected = {
        "main": baseline_clone,
        "deepcopy": lambda: deepcopy_clone,
        "cow": lambda: java_sql._SqlFlow.clone,
    }[mode]()
    copy_state = java_sql._copy_state

    def clone(flow):
        counters["clones"] += 1
        counters["materializations"] += int(mode != "cow")
        return selected(flow)

    def materialize(variables, frames):
        counters["materializations"] += 1
        return copy_state(variables, frames)

    java_sql._SqlFlow.clone = clone
    java_sql._copy_state = materialize
    content = fixture(kind)
    source = SourceFile(
        repository_id=str(REPOSITORY),
        logical_key="A.java",
        name="A.java",
        path="A.java",
        language="java",
        id=logical_id(str(REPOSITORY), EntityType.SOURCE_FILE, "A.java"),
        content_sha256=hashlib.sha256(content).hexdigest(),
    )
    captured = SourceInput(source, content)

    async def run():
        analyzer = java_sql.JavaSqlAnalyzer((captured,))
        return await analyzer((captured,))

    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    started = time.perf_counter()
    analyses = asyncio.run(run())
    seconds = time.perf_counter() - started
    usage_after = resource.getrusage(resource.RUSAGE_SELF)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
        1 if sys.platform == "darwin" else 1024
    )
    entities = sorted(
        entity.model_dump_json()
        for analysis in analyses
        for entity in analysis.entities
    )
    return {
        "mode": mode,
        "fixture": kind,
        "fixture_sha256": hashlib.sha256(content).hexdigest(),
        "seconds": seconds,
        "peak_rss_bytes": peak,
        "entities": len(entities),
        "facts_sha256": hashlib.sha256(json.dumps(entities).encode()).hexdigest(),
        "analysis_io_in_blocks": usage_after.ru_inblock - usage_before.ru_inblock,
        "analysis_io_out_blocks": usage_after.ru_oublock - usage_before.ru_oublock,
        "max_paths": java_sql._MAX_PATHS,
        **counters,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=("main", "deepcopy", "cow"))
    parser.add_argument("--fixture", choices=("read_heavy", "write_heavy"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker, args.fixture)))
        return
    results = []
    for kind in ("read_heavy", "write_heavy"):
        for mode in ("main", "deepcopy", "cow"):
            output = subprocess.check_output(
                [
                    sys.executable,
                    "-m",
                    "code_crawler.java_sql_flow_benchmark",
                    "--worker",
                    mode,
                    "--fixture",
                    kind,
                ],
                text=True,
            )
            results.append(json.loads(output))
    report = {
        "baseline": BASELINE,
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
        "source_sha256": {
            name: hashlib.sha256(
                Path(__file__).with_name(name).read_bytes()
            ).hexdigest()
            for name in ("java.py", "java_sql.py", "java_sql_flow_benchmark.py")
        },
        "results": results,
        "equivalent": all(
            len({r["facts_sha256"] for r in results if r["fixture"] == kind}) == 1
            for kind in ("read_heavy", "write_heavy")
        ),
        "limitations": "One ordered fresh-process run per mode/case. Same current analyzer with swapped clone strategies, not full old checkouts. Synthetic corpus; no production throughput or memory SLA. RSS includes imports. Clone counts are not path merging.",
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text)
    if not report["equivalent"]:
        raise SystemExit("fact mismatch")


if __name__ == "__main__":
    main()
