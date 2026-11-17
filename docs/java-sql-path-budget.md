# Java SQL path budget and overflow report

The budget is the number of retained abstract analysis paths per recovery, default
**256**. Configure it on canonical indexing with `--java-sql-max-paths N` (integer
1..65536). It is shared by SQL construction and execution-derived profiles:
`sql`, `execution`, `semantic`, `lineage`, `database`, `orm`. Nondefault settings
and reporting require a SQL-enabled Java profile.

```bash
uv run code-crawler index ../repo \
  --java-sql-max-paths 1024 \
  --java-sql-path-report /tmp/java-sql-paths.jsonl

uv run code-crawler index-sources ../repo --repository-key org/repo --publish \
  --java-sql-path-report /tmp/java-sql-default-budget.jsonl
```

The report flag is optional and creates no file when omitted. Its destination must
be **outside the indexed source root**; its parent directory must already exist.
This prevents report IO from changing captured inputs or overwriting source files.
The report is metadata for the requested analysis, not an MCP/public diagnostic API.
It contains relative source paths and symbol names and is written privately (0600).

## JSONL contents and interpretation

The first line is a version-1 `summary`: repository key, max_paths, status,
`scope="reanalyzed_methods_only"`, analyzed_methods, overflow_cases. A completed
index adds snapshot_id, reused_files and reanalyzed_files. File counts describe the
whole incremental source plan; case rows identify Java callables only.

Each following `case` identifies a method/constructor that actually pruned states:
repository UUID, relative path, content_sha256, canonical owner_id, qualified_name,
symbol_kind, start/end line and exclusive byte offsets, configured limit,
retained_paths, pruning_events and attempted_paths_lower_bound. Overloads are
disambiguated by owner ID and location. No source body, SQL text, AST dump or error
message is exported. Case detection works even when no SQL candidate was found.

Exactly reaching a budget is not an overflow. The attempted count is a **lower
bound on abstract states offered at a cut**, not the total number of feasible
runtime paths: existing pre-fork pruning can happen before children are allocated.
All existing path ordering and `path limit reached: variants truncated` reasons
remain unchanged. Truncated SQL remains partial; no inferred relation is promoted.

A report is a per-run observation, **not a complete repository census**. Unchanged
files can be reused without visiting their methods; a no-change run may produce
only a summary with analyzed_methods=0 and reused_files>0. Parser/catalog fallback
can also prevent SQL method recovery; canonical SourceAnalysis retains its normal
Coverage/diagnostics. An empty case list does not prove all methods fit the budget.
Changing the report filename does not invalidate reusable facts.

## Lifecycle, retry and publication

Callbacks spool small metadata records in the analysis worker; file export runs
through to_thread. The final JSONL is atomically replaced after indexing and before
publication. ANALYZED means the BUILDING snapshot was constructed, not that it was
validated/published. A later publication failure leaves that analysis report usable.
On analysis/export failure, a best-effort FAILED report preserves partial cases and
known snapshot metadata. If export itself fails, the original error remains primary.
Existing output stays intact until successful replacement. Late callbacks from a
cancelled synchronous worker are ignored after sealing. Hard process termination
may lose unexported observations; this is not a crash-durable tracing service.

Failure exporting a requested report fails the job before publication; the old
pointer remains unchanged and a built snapshot is tracked for normal recovery/GC.
`jobs retry JOB_UUID` restores the effective budget and absolute report destination;
new jobs also store the resolved source root. Retrying replaces the report for that
attempt. Old saved jobs without these keys use default 256 with reporting disabled.

Budget is encoded in the bound Java analysis version. Changing it invalidates Java
facts rather than reusing results from a different limit. This release explicitly
encodes the default too, so upgrading may cause one initial Java reanalysis. Older
published snapshots remain immutable/readable. Diagnostic callbacks/paths never
enter analysis identity. There is no migration or new canonical entity kind.

Higher budgets can greatly increase CPU/RSS. The cap is not a memory guarantee:
intermediate branch results can exceed the number of retained states. Loops retain
the existing zero/one-iteration approximation. No literal pruning or equivalent
state merging is introduced.

## Library configuration

Pass `SqlPathOptions(max_paths=1024, on_method=callback)` to `JavaSourceAdapter` as
`sql_options`, to any SQL-derived analyzer, or to the `index_java_*` convenience
API. The optional callback receives a PathLimitCase on overflow, None for another
analyzed callable. It runs synchronously in the analyzer worker; the CLI owns its
file sink. Each recovery has independent counters and a per-flow budget, so
concurrent analyzers cannot change one another's configuration.
