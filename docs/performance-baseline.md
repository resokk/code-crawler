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
but are excluded from successful-stage distributions. Successful early stages of
a later failing run still contribute. This synthetic series establishes a baseline
on one host; it is not a production SLO or a reliable tail-latency estimate. Warm
queries and fixed scale order do not establish cold-cache or causal speedups.

## Recorded series

Results and exact implementation SHA will be attached after the controlled run.
