# Java source text cache completion receipt

Implementation: [`2051acf`](https://github.com/resokk/code-crawler/commit/2051acf3b8e2d8e93202ce806d0257fba13f53c1).
[Required PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/44128993631)
passed: **1431 tests in 200.77s**, including all migrations, lint/format and
clean-working-tree checks. Local full suite: 1182 passed / 249 PostgreSQL tests
skipped (19.92s); separate local mandatory PG15 construction/execution/semantic/
lineage storage: 8 passed (11.86s), JPA/registry: 4 passed (10.53s).
PR: https://github.com/resokk/code-crawler/pull/20.

Acceptance: tests/test_java_text_cache.py covers retained Node identity across
trees, repeated wrappers, empty/None, UTF-8 replacement and parse diagnostics,
entry/byte caps, failures, nested helpers, simultaneous workers, actual 64-file
slice scopes and cancelled-to_thread cleanup in the worker. Complete construction,
execution and cross-file ORM payloads match direct decoding. Existing Java/profile
and PostgreSQL roundtrip/publication regressions pass in required CI.

Delivered: thread-local bounded text scopes at synchronous parser/extractor and
all Java profile per-file analysis boundaries. Nested helper scopes reuse the
active cache; finally releases retained Node/text keys. No cross-file global dict,
new dependency, SQL pruning/path merging, path-limit/schema or publication change.

Benchmark: three fresh processes per mode/case, alternating order; direct mode
restores pre-cache entry points. Full fact digests match across every sample.
- 24 small files: median 0.08790s -> 0.08198s; median RSS 49.15 -> 49.06 MiB.
- Four SQL-path files: 3.36623s -> 3.29872s (about 2.0%); median RSS
  75.57 -> 75.84 MiB. 345412 hits / 351340 calls; 5928 actual decodes.
- Peak admitted strings per SQL scope: 27709 bytes; caps are 8192 entries / 1 MiB.

Raw samples, fixture/fact/source/lock hashes, versions, CPU/RAM/cgroup, cache
counts and I/O: docs/benchmarks/java-source-text-cache-2026-11-17.json.
Contract/reproduction: docs/java-source-text-cache.md. Measurements are synthetic,
include numeric instrumentation and are not a production SLA. Cache lookup costs
remain; process RSS can increase. Node/dict overhead is separate from text bytes.
Cancelled async callers do not terminate synchronous workers; cleanup happens
when those workers finish. The private scope must not span awaits/multi-file loops.
PR remains unmerged.
