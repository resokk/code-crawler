"""Linux opt-in 1/2/4 Java preparation benchmark with sampled process-tree RSS."""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

from code_crawler.incremental import SourceInput
from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.java_sql_flow_benchmark import fixture
from code_crawler.sql_paths import SqlPathOptions
from code_crawler.ucm import EntityType, SourceFile, logical_id


def sources(case: str) -> tuple[SourceInput, ...]:
    repo = "11111111-1111-1111-1111-111111111111"
    result = []
    for i in range(32 if case == "catalog_heavy" else 8):
        if case == "small":
            content = f"class C{i} {{void m(){{}}}}".encode()
        elif case == "catalog_heavy":
            content = fixture("read_heavy").replace(
                b"class A ", f"class C{i} ".encode()
            )
        else:
            locals_ = "".join(f'String v{j}="value{j}";' for j in range(4))
            body = (
                locals_
                + 'String q="select id from users";use(q);'
                + "if(f){touch();}else{touch();}" * 18
                + "use(q);"
            )
            content = f"class C{i} {{void m(boolean f){{{body}}}}}".encode()
        path = f"C{i}.java"
        file = SourceFile(
            repository_id=repo,
            id=logical_id(repo, EntityType.SOURCE_FILE, path),
            logical_key=path,
            name=path,
            path=path,
            language="java",
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        result.append(SourceInput(file, content))
    return tuple(result)


def process_tree(pid: int) -> dict[int, str]:
    parents: dict[int, list[int]] = {}
    identities = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            parents.setdefault(int(fields[1]), []).append(int(entry.name))
            identities[int(entry.name)] = fields[19]
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    pending, seen = [pid], {}
    while pending:
        current = pending.pop()
        if current in seen or current not in identities:
            continue
        seen[current] = identities[current]
        pending.extend(parents.get(current, ()))
    return seen


def memory_sample(identities: dict[int, str]) -> tuple[int, int]:
    rss, live = 0, 0
    for pid, identity in identities.items():
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            if fields[19] != identity:
                continue
            rss += int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * os.sysconf(
                "SC_PAGE_SIZE"
            )
            live += 1
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rss, live


def worker(count: int, case: str) -> dict:
    captured = sources(case)
    stopped = threading.Event()
    peaks = {"aggregate_rss_bytes": 0, "process_count": 1, "samples": 0}

    holder = []

    def sample():
        identities = {
            os.getpid(): Path("/proc/self/stat")
            .read_text()
            .rsplit(")", 1)[1]
            .split()[19]
        }
        signature = ()
        while not stopped.is_set():
            pool = holder[0]._parallel if holder else None
            if pool is not None and pool.pids != signature:
                signature = pool.pids
                identities.update(process_tree(os.getpid()))
            rss, processes = memory_sample(identities)
            peaks["aggregate_rss_bytes"] = max(peaks["aggregate_rss_bytes"], rss)
            peaks["process_count"] = max(peaks["process_count"], processes)
            peaks["samples"] += 1
            stopped.wait(0.025)

    sampler = threading.Thread(target=sample)
    sampler.start()

    async def run():
        prepared = await JavaSourceAdapter(
            profile="sql",
            analysis_workers=count,
            sql_options=SqlPathOptions(4096 if case == "cpu" else 256),
        ).prepare(captured)
        holder.append(prepared)
        version = prepared.analysis_version
        output = []
        analysis_start = time.perf_counter()
        try:
            for start in range(0, len(captured), 64):
                output.extend(await prepared(captured[start : start + 64]))
        finally:
            await prepared.aclose()
        return version, output, time.perf_counter() - analysis_start

    before = resource.getrusage(resource.RUSAGE_SELF)
    child_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.perf_counter()
    try:
        version, output, analysis_seconds = asyncio.run(run())
        seconds = time.perf_counter() - started
        records = [result.model_dump_json() for result in output]
    finally:
        stopped.set()
        sampler.join()
    after = resource.getrusage(resource.RUSAGE_SELF)
    child_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "parent_cpu_seconds": after.ru_utime
        + after.ru_stime
        - before.ru_utime
        - before.ru_stime,
        "joined_children_cpu_seconds": child_after.ru_utime
        + child_after.ru_stime
        - child_before.ru_utime
        - child_before.ru_stime,
        "io_in_blocks": after.ru_inblock
        + child_after.ru_inblock
        - before.ru_inblock
        - child_before.ru_inblock,
        "io_out_blocks": after.ru_oublock
        + child_after.ru_oublock
        - before.ru_oublock
        - child_before.ru_oublock,
        "workers": count,
        "max_paths": 4096 if case == "cpu" else 256,
        "case": case,
        "files": len(captured),
        "seconds": seconds,
        "analysis_and_worker_lifecycle_seconds": analysis_seconds,
        "analysis_version": version,
        "facts_sha256": hashlib.sha256(json.dumps(records).encode()).hexdigest(),
        "fixture_sha256": hashlib.sha256(
            b"\0".join(source.content for source in captured)
        ).hexdigest(),
        "entities": sum(len(result.analysis.entities) for result in output),
        **peaks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=int, choices=(1, 2, 4))
    parser.add_argument("--case", choices=("small", "cpu", "catalog_heavy"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not Path("/proc/self/statm").exists():
        parser.error("this memory measurement requires Linux /proc")
    if args.worker:
        print(json.dumps(worker(args.worker, args.case)))
        return
    results = []
    for case in ("small", "cpu", "catalog_heavy"):
        for count in (1, 2, 4):
            result = subprocess.check_output(
                [
                    sys.executable,
                    "-m",
                    "code_crawler.parallel_benchmark",
                    "--worker",
                    str(count),
                    "--case",
                    case,
                ],
                text=True,
            )
            results.append(json.loads(result))
    root = Path(__file__).parent
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "physical_memory_bytes": os.sysconf("SC_PHYS_PAGES")
        * os.sysconf("SC_PAGE_SIZE"),
        "base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "uv_lock_sha256": hashlib.sha256(
            root.parents[1].joinpath("uv.lock").read_bytes()
        ).hexdigest(),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("tree-sitter", "tree-sitter-java", "sqlglot")
        },
        "cgroup": {
            name: Path("/sys/fs/cgroup", name).read_text().strip()
            for name in ("cpu.max", "memory.max")
            if Path("/sys/fs/cgroup", name).exists()
        },
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "java_parallel.py",
                "java_adapter.py",
                "parallel_benchmark.py",
                "java_sql_flow_benchmark.py",
            )
        },
        "results": results,
        "equivalent": all(
            len({r["facts_sha256"] for r in results if r["case"] == case}) == 1
            for case in ("small", "cpu", "catalog_heavy")
        ),
        "limitations": "One ordered fresh-process run per count/case. /proc sampling every 25ms sums simultaneous RSS of parent and descendants, including spawn helper via one-time PPID discovery at pool startup and checked process start identities, and double-counts shared pages. Preparation includes parent catalogue, child startup/reconstruction, IPC and shutdown; excludes database and parent UCM row normalization. Synthetic evidence, not a production SLA.",
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
