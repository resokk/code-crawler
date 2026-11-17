# Java source text cache

`java._text` reuses decoded Tree-sitter node text during a synchronous file
operation. Enabled by default for `java.analyze`, Java symbol extraction and the
calls/SQL/execution/semantic/lineage/database/ORM per-file analysis entry points.
Nested helpers reuse the current scope. A 64-file worker slice gets a fresh scope
for every file; catalogue preparation/extraction and later analysis use separate
scopes, never a persistent catalogue text cache.

The slot is thread-local and established inside the worker, not in the async
caller. `asyncio.to_thread` ContextVar propagation cannot share this slot between
threads. Scope exit clears Node/text references and restores the previous slot in
`finally`, including errors. Cancelling the async caller does not terminate a
running Python worker: that worker clears its cache when its synchronous operation
finishes. The private scope must not span awaits or a multi-file loop.

Retained `Node` handles are keys. Their trees stay alive until scope exit, so a
recycled `node.id` cannot produce stale text, including references to other live
catalogue trees. Existing analysis treats source bytes/trees as immutable; no tree
edits occur inside the scope. No global dict or cross-file identity cache exists.
Outside a scope `_text` decodes directly. `None` returns `""`; empty strings are
cached using a distinct miss sentinel. UTF-8 `errors="replace"` is unchanged.
Invalid input handling in `java.analyze` still reports INVALID_UTF8.

Fixed caps: **8192 entries and 1 MiB decoded strings** (`sys.getsizeof` includes
string-object storage). Node/dict overhead is separately bounded by entry count.
Over-cap values are decoded without admission; there is no unbounded growth,
eviction churn or operator tuning flag. Cache counters retain numbers only.
Returned UCM text still lives as long as the facts that need it; clearing the
cache releases its own references, not application results.

No analysis/version/schema/publication change, literal-based pruning or path
merging. SQL uses its configured path budget (default 256) and existing partial reasons;
the text cache does not change them. Existing
published snapshots and archived source bytes are unaffected.

## Reproducible measurement

```bash
uv run python -m code_crawler.java_text_benchmark --output /tmp/java-text-cache.json
```

Fixed ORM pipeline, three fresh processes per mode/case, alternating order.
Direct mode restores pre-cache entry points and UTF-8 decoding. Both modes include
numeric call-count instrumentation. Complete entity digests match across all runs.
Timing covers analyzer construction and analysis; peak process RSS includes imports
and fact serialization. Results are synthetic measurements, not a production SLA.

| Corpus | Direct median, s | Cached median, s | Direct → cached RSS, MiB |
| --- | ---: | ---: | ---: |
| 24 small Java files | 0.08790 | 0.08198 | 49.15 → 49.06 |
| 4 files with repeated SQL paths | 3.36623 | 3.29872 | 75.57 → 75.84 |

Observed median improvement: 6.7% for small files, 2.0% for SQL paths. With only
three processes, these are not statistical guarantees. SQL helper calls: 351340;
cache hits: 345412 (98.3%); actual decodes: 5928 including calls outside scopes.
Peak admitted strings per SQL scope: 27709 bytes. Small-file hits: 408/792 (51.5%).
A profile's 5.7% helper share is not an expected end-to-end speedup: lookup/counter
costs remain, and RSS can increase. Node/dict overhead is not the admitted-text
counter. No reduction in the number of paths or false completeness claim occurs.

[Raw report](benchmarks/java-source-text-cache-2026-11-17.json) includes all samples,
full fact/fixture/source hashes, lockfile hash, dependency/Python/platform versions,
CPU/RAM/cgroup, hits/misses, scope counts, peak RSS and analysis process I/O blocks.
No SQL/source bodies are included in that report.
