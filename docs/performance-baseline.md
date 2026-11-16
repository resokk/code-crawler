# PG15 end-to-end performance baseline (B01)

`python -m code_crawler.performance_baseline` measures the current schema and real
Java/ORM captured-source pipeline. It complements the historical query-index
comparison in [query-indexes.md](query-indexes.md) and the isolated synthetic
FK workload in [ucm-ingestion.md](ucm-ingestion.md).

## Reproduction

Use a dedicated, otherwise idle PostgreSQL **15** server with CREATEDB privileges.
The admin URL is read only from the environment and is never written to reports.
The runner creates a randomly named `crawler_baseline_<uuid>` database per trial,
initializes all migrations, and drops only that database in `finally`, including
when the child process times out or exits abnormally. It never initializes or
collects garbage in the admin database. No application configuration or MCP tool
is added. Temporary Git fixtures and checkpoint files are also owned by the runner.

```sh
BENCHMARK_DATABASE_URL=postgresql://.../postgres \
  uv run python -m code_crawler.performance_baseline \
  --output /tmp/end-to-end-pg15.json
```

Defaults: groups `199 499 1500` produce exactly **400**, **1,000**, **3,002** Java
files. The first scale runs three times in fresh worker processes/databases; the
larger scales run once each. Each reader query has two warmups and seven recorded
wall-time samples, followed by actual SQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`.
`--groups`, `--trials`, `--repeats`, `--timeout` (per trial, default 1,800 seconds)
and `--gc-timeout` (default 120 seconds) make budgets explicit. Small CI smoke tests
use groups=1, not a noisy large-scale performance threshold.

The deterministic fixture generator is shared with `query_benchmark`: JDBC
statements, calls across services and duplicate type candidates, Java `orm`
profile. Fixture hash, file/byte counts, entity-type counts, implementation Git SHA,
dirty-tree status, dependency lock hash, Python/PG versions, host CPU/RAM, container
limits and relevant PostgreSQL settings accompany every series. Counts establish
whether the large attempt actually exceeds one million entities; a requested size
alone is not a successful large-snapshot result.

## Measurements and failure semantics

Each run records capture, registry preparation, analysis slices, temporary-table
staging, transfer, deferred FK checks, source archival, index total, semantic
validation, publication, readers, no-change incremental clone and GC separately.
Instrumentation wraps the real calls only inside the benchmark worker; it does
not alter transaction boundaries, disable constraints or change canonical facts.
On current B04 code the FK measurement includes refreshing planner statistics.
The difference between index total and named nested stages includes row conversion,
manifest/dependency writes, verification and transaction overhead; it is not hidden
as analyzer time. Do not sum index total with its nested stages.

GC operates on an unpublished, real no-change incremental clone, while the original
published snapshot remains the reader reference. Results are compared before and
after GC. GC timeout rolls back the normal GC transaction; the report retains the
failure, partial timing, and post-timeout reader comparison. Other exceptions retain
their class and last stage without serializing arbitrary error details. Parent
checkpoints preserve the latest completed stage when a worker is killed. A signal
exit is not automatically called OOM: it can have other causes.

Stage events contain elapsed seconds, cumulative client peak RSS, user/system CPU,
page faults, block IO and Linux `/proc/self/io` counters, plus cluster WAL LSN deltas.
Full-run PG database counters, relation statistics/sizes and before/after WAL LSNs
are retained. Peak RSS is a per-process high-water mark, not additional memory
allocated by a stage; client process IO does not measure PostgreSQL backend IO.
PG buffers/stats and EXPLAIN supply server observations. Database counters can lag
and include instrumentation, and WAL deltas include any other cluster activity.
`track_io_timing=off` means zero server IO times are unavailable timing, not free IO.

Raw successful samples and min/max/median/mean/sample standard deviation are
reported for each scale/stage. Failed or cancelled stage events remain in `runs`
but are excluded from successful-stage distributions. Successful complete early stages of
a later failing run still contribute. Incomplete slice-loop totals are excluded
from whole-workload distributions until indexing succeeds. This synthetic series establishes a baseline
on one host; it is not a production SLO or a reliable tail-latency estimate. Warm
queries and fixed scale order do not establish cold-cache or causal speedups.

## Recorded series

Measured implementation: `6eaa9841d9a1b4352ac8714c758d3b684afb8bf3`, clean tree.
[Compact report](benchmarks/end-to-end-pg15-2026-11-16.json),
[unchanged raw report, gzip](benchmarks/end-to-end-pg15-2026-11-16.raw.json.gz),
[disk guard observations](benchmarks/end-to-end-pg15-2026-11-16.disk-guard.json).
The raw report SHA256 is
`d0c8c1f6871b9c214cca39c03ae979a2373ff2a9547cf3bc446924f9853a6bdf`.
The compact report records compressed/raw hashes and summarizer/guard source hashes.

Host: Linux 6.18.57 x86_64, AMD EPYC 9V74, container quota **2 CPUs / 8 GiB**;
Python 3.12.14, PostgreSQL 15.20 Debian. PG: locale en_US.utf8,
shared_buffers=128MB, work_mem=4MB, maintenance_work_mem=64MB,
plan_cache_mode=auto, fsync/synchronous_commit/full_page_writes=on,
track_io_timing=off. The local PGDATA filesystem was 7.9 GiB with about 2.6 GiB
available before the series. No concurrent local test suite ran during measurement.

Every 400-file trial published **140,717** entities, and the 1,000-file trial
published **352,817**. The 3,002-file workload targets the previously demonstrated
~1.06M-entity generator scale, but **did not finish indexing on this host**.
No million-entity success, semantic validation or publication is claimed here.

Seconds below are successful complete-stage totals. The first column is the median
of three independent 400-file trials; raw samples/distributions remain in JSON.



| Stage | 400 files, median | 1,000 files | 3,002-file attempt |
| --- | ---: | ---: | ---: |
| Capture | 0.033 | 0.096 | 0.190 |
| Prepare | 3.784 | 9.111 | 33.897 |
| Analyze (all slices) | 37.298 | 108.440 | not completed |
| Stage (all slices) | 2.748 | 8.330 | not completed |
| Transfer (all slices) | 15.758 | 47.077 | stopped: disk reserve |
| FK + ANALYZE | 10.761 | 24.946 | not completed |
| Source archive | 0.038 | 0.084 | not completed |
| Index total (includes nested stages) | 92.576 | 258.442 | not completed |
| Validation | 43.132 | 130.865 | not completed |
| Publication | 0.433 | 0.887 | not completed |
| Reader profiling total | 0.906 | 0.915 | not completed |
| Incremental clone | 33.471 | stopped: disk reserve | not completed |
| GC | timeout 120 s × 3 | not completed | not completed |

Index samples: 92.283 / 92.576 / 93.094 s; validation samples:
40.792 / 43.132 / 51.347 s. Client RSS peaks for the three 400-file trials were
414.0 / 419.5 / 414.6 MiB. Their end database sizes were 734.6–735.9 MiB including
the cancelled clone/GC workload; cluster WAL deltas were 1,295.8–1,325.0 MiB.
These sizes are not the size of one clean published snapshot.

All three GC attempts exceeded 120 seconds, rolled back, and preserved the
published pointer and identical reader results. They provide a censored lower
bound, not a GC latency distribution or a completed-GC throughput number.
The 1,000-file worker was stopped on **clone** at 528,424,960 free bytes, with
577,620 KiB client peak RSS; the 3,002-file worker was stopped on **transfer** at
531,554,304 free bytes, with 1,045,068 KiB client peak RSS. Both exited via SIGTERM
and parent-owned DB cleanup completed. Their uncompleted stages and end-of-run
server counters are unavailable, not zero. There was no observed OOM.

The raw format-v1 report is preserved byte-for-byte. Its interrupted-loop slice
sums are partial observations. The compact format-v2 summary and current runner
use `stage_distributions`: successful analyze/stage/transfer totals enter a scale
distribution only after index completed. This reporting correction is regression
tested against interrupted and completed runs; it does not change measured calls.
To inspect full plans and raw process/DB metrics:

```sh
uv run python -c 'import gzip,json; r=json.load(gzip.open("docs/benchmarks/end-to-end-pg15-2026-11-16.raw.json.gz")); print(r["runs"][0]["queries"]["table_readers"]["plans"])'
```

Example warm API median wall times (ms; 400-file range of three trial medians).
These are in-process structural/typed-reader calls, excluding MCP HTTP transport
and authentication latency:

| API | 400 files | 1,000 files |
| --- | ---: | ---: |
| symbol_simple | 3.09–3.72 | 4.94 |
| callers | 1.85–3.05 | 2.49 |
| table_readers | 7.38–10.63 | 8.69 |
| column_writers | 7.03–8.46 | 10.32 |
| trace_out | 5.52–7.84 | 9.27 |
| typed_entity | 4.89–5.65 | 4.49 |

The baseline identifies two concrete follow-ups: B06 must measure and improve GC
beyond the current budget; another >1M attempt needs enough PGDATA/WAL disk space.
It does not establish a scalability ceiling or a production SLO. B02/B03/B05 remain
separate work; no indexing/validation optimization is introduced here.

## Local disk reserve supervisor

On this host, Docker PGDATA and `/workspace` share the same 7.9 GiB filesystem.
During the 400-file series only about 928 MiB remained; a separate supervisor was
therefore enabled with a 512 MiB reserve before the larger attempts. It sends
SIGTERM only to a verified direct `performance_baseline --worker` child of the
specified parent. The parent then records the signal exit, retains the checkpoint
and drops its own DB. No PostgreSQL process is signaled. The companion JSON records
observed free bytes, stopped workload, worker peak RSS, checkpoint and signal.

For a reproducible guarded run, use the Python parent PID (not a uv wrapper PID):

```sh
BENCHMARK_DATABASE_URL=postgresql://.../postgres \
  .venv/bin/python -m code_crawler.performance_baseline \
  --output /tmp/end-to-end-pg15.json &
baseline_pid=$!
.venv/bin/python -m code_crawler.performance_baseline_guard \
  --parent-pid "$baseline_pid" --filesystem /workspace --reserve-mib 512 \
  --output /tmp/end-to-end-pg15-disk-guard.json &
guard_pid=$!
wait "$baseline_pid"
wait "$guard_pid"
```

The monitored path must be verified to share the PostgreSQL data filesystem;
local free space cannot establish capacity on a remote PostgreSQL server.
Guard-stopped attempts are resource-limited failures, not successes or OOMs.
