import asyncio
import multiprocessing as mp
import os
import time
from dataclasses import replace

import pytest
from test_java_calls import source

from code_crawler.java_adapter import JavaSourceAdapter
from code_crawler.java_parallel import JavaProcessPool, WorkerConfig
from code_crawler.sql_paths import SqlPathOptions


def captured():
    return (
        source(
            "A.java",
            'import org.springframework.web.bind.annotation.*; @RestController class A {@GetMapping("/a") String m(boolean f){String q="select id from t";if(f){q+=" where id=1";}else{q+=" order by id";}return q;}}',
        ),
        source("B.java", "class B {void m(){new A().m(true);}}"),
        source(
            "C.java",
            'import java.sql.*;class C {void m(Connection c) throws Exception {c.prepareStatement("delete from t").execute();}}',
        ),
        source(
            "D.java",
            'import jakarta.persistence.*;@Entity @Table(name="users") class D {@Id long id; String name;}',
        ),
    )


def config():
    return WorkerConfig(
        captured(), "sql", (), (), "postgres", "UNKNOWN", 256, False, "invalid-version"
    )


def dead_worker(pipe, config):
    pipe.send(("ready", None))
    pipe.recv()
    os._exit(17)


def blocked_worker(pipe, config):
    pipe.send(("ready", None))
    pipe.recv()
    time.sleep(60)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, 33])
def test_invalid_workers_rejected(value):
    with pytest.raises(ValueError, match="1..32"):
        JavaSourceAdapter(analysis_workers=value)


@pytest.mark.parametrize("workers", [2, 4])
def test_complete_orm_facts_order_callbacks_and_version_match(workers):
    async def run(count):
        from test_java_database import document

        events = []
        prepared = await JavaSourceAdapter(
            profile="orm",
            schemas=(document(),),
            analysis_workers=count,
            sql_options=SqlPathOptions(1, events.append),
        ).prepare(captured())
        try:
            output = await prepared(captured())
            pids = prepared._parallel.pids if prepared._parallel else ()
            return (
                prepared.analysis_version,
                tuple(r.model_dump_json() for r in output),
                events,
                pids,
            )
        finally:
            await prepared.aclose()

    sequential = asyncio.run(run(1))
    parallel = asyncio.run(run(workers))
    assert sequential[:3] == parallel[:3]
    assert len(parallel[3]) == workers and os.getpid() not in parallel[3]
    assert not set(parallel[3]) & {p.pid for p in mp.active_children()}


def test_catalogue_failure_and_crash_abort_all_processes():
    async def run(target, match):
        pool = JavaProcessPool(config(), 2, _target=target)
        pids = pool.pids
        try:
            with pytest.raises(RuntimeError, match=match):
                await asyncio.wait_for(pool.analyze(captured()), timeout=15)
        finally:
            await pool.aclose(abort=True)
        assert not set(pids) & {p.pid for p in mp.active_children()}

    asyncio.run(run(None, "catalogue version"))
    asyncio.run(run(dead_worker, "exited"))


def test_cancel_terminates_inflight_workers():
    async def run():
        pool = JavaProcessPool(config(), 2, _target=blocked_worker)
        pids = pool.pids
        task = asyncio.create_task(pool.analyze(captured()))
        try:
            for _ in range(250):
                if all(worker.ready for worker in pool._workers):
                    break
                await asyncio.sleep(0.02)
            assert all(worker.ready for worker in pool._workers)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            await pool.aclose(abort=True)
        assert not set(pids) & {p.pid for p in mp.active_children()}

    asyncio.run(run())


def test_captured_source_mismatch_is_rejected_before_spawn():
    async def run():
        prepared = await JavaSourceAdapter(profile="sql", analysis_workers=2).prepare(
            captured()
        )
        try:
            with pytest.raises(ValueError, match="catalog"):
                await prepared((replace(captured()[0], content=b"changed"),))
            assert prepared._parallel is None
        finally:
            await prepared.aclose()

    asyncio.run(run())


def test_hard_parent_death_stops_owned_workers(tmp_path):
    import json
    import signal
    import subprocess
    import sys
    from pathlib import Path

    if not Path("/proc/self/stat").exists():
        pytest.skip("Linux process-state assertion")
    ready = tmp_path / "pids.json"
    code = f"""
import json,sys,time
from pathlib import Path
sys.path.insert(0, {str(Path(__file__).parent)!r})
from test_java_parallel import config,blocked_worker
from code_crawler.java_parallel import JavaProcessPool
pool=JavaProcessPool(config(),2,_target=blocked_worker)
for worker in pool._workers:
    worker.receive("ready")
    worker.pipe.send(("blocked",))
Path({str(ready)!r}).write_text(json.dumps(pool.pids))
while True: time.sleep(60)
"""
    parent = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    identities = {}

    def alive(pid):
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            return fields[0] != "Z" and fields[19] == identities[pid]
        except FileNotFoundError:
            return False

    try:
        deadline = time.monotonic() + 15
        while (
            not ready.exists() and parent.poll() is None and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert ready.exists()
        pids = json.loads(ready.read_text())
        for pid in pids:
            identities[pid] = (
                Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
            )
        parent.kill()
        parent.wait(timeout=10)
        deadline = time.monotonic() + 10
        while any(alive(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not any(alive(pid) for pid in pids)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=10)
        for pid in identities:
            if alive(pid):
                os.kill(pid, signal.SIGKILL)
