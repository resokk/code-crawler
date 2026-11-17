# Design

An immutable SqlPathOptions carries a validated 1..65536 max_paths (default 256)
and optional method diagnostic callback through SQL/execution/semantic/lineage/
database/ORM analyzers. Each recovery flow owns its budget; clones share only that
recovery's diagnostic counters. No mutable global setting is changed. Java analysis
versions encode the effective budget, so incremental reuse cannot cross budgets.
A callback/destination does not affect fact identity or versioning.

The existing pre-fork limiter can discard states before allocating children.
Diagnostic attempted_paths_lower_bound therefore reports the largest observed
state count offered at a cut (pre-fork counts multiplied by two), never claims the
exact total number of feasible runtime paths. Exactly the budget without pruning
is not overflow. All prior partial reasons/path ordering remain in place.
Construction recovery emits one method/constructor diagnostic even when no SQL
was found. Execution recovery uses the same budget without duplicating the report.

An optional CLI-owned, locked spool collects callback metadata. File IO runs in
workers/to_thread; adapters only receive a callback. Reports are atomically replaced
with private permissions. Export completes after indexing and before publication;
an export failure cannot publish the new snapshot. On analysis failure a best-effort
FAILED report preserves partial observations and the original error. Cancellation
can leave a synchronous worker running; sealed reporters ignore later callbacks.
Output must be outside the indexed root to avoid source capture/overwrite conflicts.

JSONL begins with a versioned summary: status, repository, effective limit,
analyzed-method/case counts, snapshot ID when available, reuse/reanalysis counts,
and scope=reanalyzed_methods_only. Subsequent records contain source hash, relative
path, canonical owner/name/kind, source coordinates, retained paths and pruning
counters. No SQL, source body, exception message or arbitrary AST text is exported.
Retry stores effective budget and absolute report destination; old jobs use defaults.
