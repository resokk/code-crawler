# Operational metrics and coverage (E01)

Operational observations are derivatives, separate from immutable UCM. Migration
0031 stores one bounded stage aggregate per operation/repository/job attempt.
No source text, paths, query arguments, exception messages or free-form reasons
are stored. Metrics never change publication pointers or evidence.

The MCP `get_monitoring` tool requires the deployment `monitor` permission and
membership of the requested repository. A deployment policy is the workspace
boundary; no caller-supplied identity or workspace overrides it. Other read
permissions do not grant monitoring. Database owners retain administrative SQL
access, including global GC observations (repository_id NULL).

The report includes request/stage counts, errors, row/candidate/truncation counts,
DB elapsed time, resolver cache hits/misses, P50/P95 wall time and process peak RSS.
Stage times are nested, not additive; per-request repeated stage calls aggregate
before persistence. RSS is process lifetime high-water, not per-job allocation.
Cross-repository searches count once for each authorized participating repository.
Results/candidates mean returned items, not unseen total matching rows. Truncation
counts responses that explicitly report truncation. Query timing uses asyncpg's
query logger; COPY and client preparation remain in stage wall time.

Metrics use fixed stage labels; repository/job IDs are scope columns, never
per-symbol labels. No raw SQL, symbol IDs, fingerprints or dynamic reason labels.
Reports cover at most 30 days and return at most 32 stage aggregates. Operators
should periodically delete old `operational_observations` rows according to their
retention policy; rows are indexed by repository/time and independent of snapshot
GC. No metrics service or background scheduler is required.

Coverage is grouped by adapter and capability from the selected publication.
COMPLETE/PARTIAL/UNSUPPORTED are separate counts; missing analyses/capabilities
are unknown, not failures. Ratios explicitly state their denominator (reported
capabilities); diagnostics expose severity counts only. Free-form reasons may
contain source fragments and are deliberately replaced by status categories.
No inferred quality score is presented. Queries without publication return an
explicit absent coverage state. Aggregates are capped and indicate truncation.

Observation collection uses task-local state and fixed-size counters. Failure to
persist observations emits a fixed warning, never fails an otherwise successful
index/query and never replaces the original exception. Cancelled/crashed processes
may lose their unfinished observation: job recovery remains the authoritative
source of abandoned attempts. Writes occur after canonical transactions; telemetry
is not a publication gate. If the telemetry transaction itself fails, it rolls
back independently. Multiple workers share PostgreSQL, not worker memory.

Free-form incomplete-analysis reasons are reduced to five categories:
UNRESOLVED, UNSUPPORTED, PARSER_LIMITATION, DYNAMIC and OTHER_PARTIAL. Classification
is explanatory rather than a new analyzer verdict. `job_id` optionally narrows
latency observations; coverage always describes the current publication and labels
its snapshot ID. `max_attempt` and `retry_observations` describe retries observed
in the selected window, not a claim that crashed attempts emitted metrics.

Apply migrations through `code-crawler db init/migrate` before deployment. Grant
`monitor` only to intended operational principals in MCP_ACCESS_POLICY; validate
an allowed request, denied foreign scope and a read-only principal without the
grant. No privileged diagnostic endpoint is anonymous. A database failure produces
`operational metrics unavailable`; check schema/role/connectivity administratively,
without enabling SQL/source payload logging. Missing metrics do not prove success.

Library `report()` requires an active read transaction; MCP supplies it. Search
wall time measures the query implementation inside the transaction, excluding
transport/pool wait and final response redaction. Stage rows count COPY records,
including typed auxiliary rows; they are not unique UCM entity counts. Monitoring
requests themselves do not contribute to search latency percentiles.

Observation writes use a 250ms lock timeout and 2s statement timeout in their
own transaction; a stalled metrics table cannot hold a canonical write transaction
open. The MCP repository-scope lookup also has a 2s client timeout. The application
DB role needs INSERT on operational_observations and access to its identity sequence
(plus SELECT for reports); the report grant alone does not grant database ownership.
