# Parallel Java snapshot preparation

Canonical CLI accepts `--analysis-workers N` (integer 1..32, default **1**):

```bash
uv run code-crawler index ../repo --analysis-workers 2
uv run code-crawler index-sources ../repo --repository-key org/repo --publish \
  --analysis-workers 4 --java-sql-max-paths 1024 \
  --java-sql-path-report /tmp/java-paths.jsonl
```

`JavaSourceAdapter(analysis_workers=2)` exposes the same option. Jobs persist it for
retry; old jobs default to 1. Worker count is operational and does not enter the
analysis fingerprint. Changing it alone reuses unchanged facts without spawning a
pool. Standalone `index_java_*` helpers remain sequential; use the source registry
for managed parallel preparation.

## Boundary and ownership

Default 1 preserves existing to_thread behavior. Opt-in processes cover Java
calls/SQL/execution/semantic/lineage/database/ORM per-file analysis when a full
catalogue is available. Symbols/parser fallback and non-Java adapters remain
sequential. A single large file is not split between workers. Parent catalogue
construction, HTTP/Kafka/BPMN enrichment, row validation/normalization, spool writing,
PostgreSQL COPY/validation/publication and source verification remain in the parent.

Each child uses spawn, reconstructing one catalogue from the identical captured
bytes/settings and checking its analysis version. This is a consistent replicated
catalogue, not shared AST memory. No tree/Node, connection, open report stream or
external callback is pickled. Sources are not reread from the repository. Private
pipes carry only this application's config, path requests and typed results; there
is no external pickle-file endpoint.

The pool is lazy and persists across the selected source slices. Each existing
64-file slice is split into contiguous groups, with at most one request per worker
and no prefetch of later slices. Results are collected in original order. Parent
callbacks replay path-report observations in that order. Workers never touch the
report file. The parent still holds a whole current slice, not the full result set.
This is not the separate fully streaming UCM ingestion feature.

An explicit incremental `analysis_complete` callback releases prepared registry
resources after the spool is built and before canonical writes. Optional managed
prepared adapters implement `async aclose(*, abort=False)`; registry finally cleanup
also covers failures. Source adapter call/return contracts stay unchanged. Children
are terminated/joined on error/cancellation; public Process/Pipe/sentinel APIs detect
abrupt exits without an initializer respawn loop. Children monitor the parent
sentinel and stop after hard parent termination; a bootstrapping child checks it
as soon as its supervisor starts. Python's spawn resource tracker
can remain idle until the parent exits; it is not a live analysis worker.

Worker failure aborts preparation before writing a snapshot. The previous
publication and its evidence remain available. Cancellation cannot stop an ordinary
thread, but can terminate this process group. The controller closes private pipes
and reaps child processes. No process count changes published data semantics.

## Memory, profiling and measurements

N workers can hold N additional full catalogues alongside the parent's catalogue.
Startup/imports, catalogue reconstruction, IPC/pickling, serialization and parent
normalization can outweigh parallel CPU time. Memory and CPU quota, not host CPU
count alone, determine useful settings. Keep default 1 for small/incremental jobs.
The existing operational peak_rss_bytes and built-in --profile describe the parent
process; child CPU requires a profiler with subprocess support.

Reproduction on Linux:

```bash
uv run python -m code_crawler.parallel_benchmark --output /tmp/parallel-java.json
```

One ordered fresh-process run per case/count, same full fact digests for 1/2/4.
Environment: CPU quota **2 cores**, cpuset 0-2, memory limit 8 GiB. Timing includes
parent catalogue, child startup/reconstruction, per-file analysis, enrichment, IPC
and shutdown; excludes source capture, normalized UCM rows, spool/DB writes.

| Corpus | 1 worker, s | 2 workers, s | 4 workers, s |
| --- | ---: | ---: | ---: |
| 8 small files, budget 256 | 0.019 | 0.725 | 1.260 |
| 8 abstract-state CPU files, budget 4096 | 6.008 | 3.811 | 5.886 |
| 32 catalogue-heavy files, budget 256 | 6.138 | 8.805 | 12.217 |

| Corpus | 1 worker RSS, MiB | 2 workers RSS, MiB | 4 workers RSS, MiB |
| --- | ---: | ---: | ---: |
| 8 small files, budget 256 | 47.8 | 159.1 | 256.3 |
| 8 abstract-state CPU files, budget 4096 | 71.9 | 210.8 | 337.3 |
| 32 catalogue-heavy files, budget 256 | 213.6 | 538.5 | 717.1 |

RSS is a sampled simultaneous sum of parent and descendants, including the spawn
helper, with start identities checked to avoid PID reuse. It double-counts shared
pages and can miss transient peaks. Discovery scans PPID once at pool startup,
then samples known processes every 25ms to avoid repeated process-table scans
stealing CPU. One sample per scenario is not a statistical or production SLA;
other load and startup variation can affect the observed ratio. Four workers
oversubscribe this environment; they are not a recommended default.

[Raw report](benchmarks/parallel-preparation-2026-11-17.json) records fixture/fact/
source/lock hashes, versions, host/cgroup data, timings, sampled RSS/process counts,
parent/child CPU and I/O. The small/catalogue regressions are retained alongside
the CPU-case speedup. Benchmark your repository with 1/2/4 before raising workers.
