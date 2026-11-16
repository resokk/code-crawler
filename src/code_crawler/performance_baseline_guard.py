"""Optional local disk-reserve supervisor for an already-running baseline parent.

Use only when the monitored path is on the PostgreSQL data filesystem. Remote
server capacity cannot be inferred from local disk usage.
"""

import argparse
import asyncio
import os
import shutil
import signal
import time
from pathlib import Path

from code_crawler.performance_baseline import write_report


def worker_command(command: list[str], actual_parent: int, parent: int) -> bool:
    """Recognize only a direct benchmark worker, never the parent or another tool."""
    return (
        actual_parent == parent
        and len(command) > 4
        and command[1:3] == ["-m", "code_crawler.performance_baseline"]
        and "--worker" in command
    )


def observe(parent: int) -> list[dict]:
    workers = []
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            fields = dict(
                line.split(":", 1)
                for line in (path / "status").read_text().splitlines()
            )
            command = (path / "cmdline").read_bytes().decode().strip("\0").split("\0")
            if worker_command(command, int(fields["PPid"]), parent):
                workers.append(
                    {
                        "pid": int(path.name),
                        "groups": int(command[command.index("--groups") + 1]),
                        "peak_rss": fields.get("VmHWM", "").strip(),
                        "checkpoint": command[command.index("--output") + 1],
                    }
                )
        except (OSError, ValueError, KeyError):
            continue
    return workers


async def supervise(
    parent: int, filesystem: Path, minimum_free_bytes: int, output: Path
) -> None:
    """Stop only verified direct workers below a declared disk reserve; retain observations."""
    if parent <= 1 or minimum_free_bytes <= 0:
        raise ValueError("invalid parent/reserve")
    report = {
        "parent_pid": parent,
        "filesystem": str(filesystem),
        "minimum_free_bytes": minimum_free_bytes,
        "poll_seconds": 1,
        "events": [],
        "minimum_observed_free_bytes": None,
    }
    try:
        while True:
            os.kill(parent, 0)
            free = (await asyncio.to_thread(shutil.disk_usage, filesystem)).free
            report["minimum_observed_free_bytes"] = min(
                free, report["minimum_observed_free_bytes"] or free
            )
            if free < minimum_free_bytes:
                for worker in await asyncio.to_thread(observe, parent):
                    # Recheck ownership immediately before signaling to limit PID-reuse races.
                    if not any(
                        candidate["pid"] == worker["pid"]
                        and candidate["checkpoint"] == worker["checkpoint"]
                        for candidate in await asyncio.to_thread(observe, parent)
                    ):
                        continue
                    try:
                        os.kill(worker["pid"], signal.SIGTERM)
                    except ProcessLookupError:
                        continue
                    report["events"].append(
                        worker
                        | {
                            "free_bytes": free,
                            "signal": "SIGTERM",
                            "unix_time": time.time(),
                        }
                    )
                    await write_report(output, report)
            await asyncio.sleep(1)
    except ProcessLookupError:
        pass
    finally:
        await write_report(output, report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--filesystem", type=Path, required=True)
    parser.add_argument("--reserve-mib", type=int, default=512)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(
        supervise(
            args.parent_pid, args.filesystem, args.reserve_mib * 1024**2, args.output
        )
    )


if __name__ == "__main__":
    main()
