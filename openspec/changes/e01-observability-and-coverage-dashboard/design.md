# E01 design: redacted operational query dashboard

## Storage and collection
Migration 0031 adds operational_observations, a derivative table independent of
snapshot lifecycle. Repository UUID and optional job UUID/attempt scope each row;
a fixed enum of 11 stages bounds per-operation cardinality. Each stage accumulates
numeric calls/errors/time/rows/truncations/cache outcomes, then writes once per
participating repository. No dynamic labels, SQL arguments, exception payloads,
paths or UCM IDs are retained. Process lifetime RSS high-water is measured at flush.

A task-local ContextVar holds an Observation. Async context managers restore it
under failure and cancellation. Incremental CPU preparation/analysis, COPY staging,
transfer, deferred FK flush, validation/publication and GC are timed at their
existing boundaries. Adapter catalogue preparation is also in prepare. Repeated
stage calls aggregate; nested times are deliberately non-additive. Ingest CLI
attaches the durable job ID and current attempt, including retries. Global GC is
admin-only and never attributed wholesale to individual repositories.

MCP begins collection only after authentication and authorization. Its canonical
query remains repeatable-read/read-only; observations flush afterward on the same
free connection, in their own transaction. asyncpg query_logger contributes DB
elapsed/error counters without retaining query strings. Results count returned
items/candidates and explicit truncation; resolver-cache hooks count HIT/MISS.
Cross-repository requests are recorded once per authorized participating repo.

Metrics persistence is best effort. SQL failure rolls back the derivative write,
emits only a fixed warning and preserves the original operation result/exception.
Process kill, cancellation or unavailable DB can lose an unfinished observation;
existing job recovery remains authoritative. No long canonical transaction or
additional source capture is introduced. Public library operations are timed when
called inside recording; CLI jobs and MCP supply the recording boundary.

## Query and access
get_monitoring(repository_key, days=7, job_id=None) requires a new explicit monitor
permission plus repository membership, checked before acquiring a DB connection.
Deployment policy defines the workspace boundary. Privileged Python report() and
SQL access remain administrative, matching existing reader APIs.

Reports aggregate numeric counters and P50/P95 of per-operation stage totals,
scoped to the selected repository/job and a validated 1..30 day window. Reports
return at most 32 stage groups. No worker-local percentile cache is used. The
repository/time index supports bounded time-window access. Storage retention is
an explicit operator policy; there is no new scheduler or monitoring service.

Coverage reads the selected publication in the caller's repeatable-read
transaction and pins it against GC. Adapter/capability/status groups are capped
at 128 with an explicit truncation flag. Missing publication, missing analyses,
and unreported capabilities remain explicit unknowns. The complete ratio uses
reported capabilities as denominator, never all possible language capabilities.
Diagnostics expose severity counts. Reasons map to five fixed categories
(UNRESOLVED, UNSUPPORTED, PARSER_LIMITATION, DYNAMIC, OTHER_PARTIAL); raw reasons
and messages are never returned. These categories explain incompleteness without
promoting it to a parser failure or a trustworthy relation.

## Validation and limitations
Unit tests cover bounded labels, numeric-only payloads, concurrent task isolation,
original-error preservation, invalid windows, distinct monitor grants and denied
foreign scope before DB access. PG15 tests run real parallel Java indexing,
publication, partial SQL coverage, counters/truncation/cache percentiles and
injected observation constraint failure. Existing HTTP two-principal tests now
include monitoring. Existing snapshot failure/GC/evidence regressions remain gates.

No web hosting/UI, infrastructure exporter, per-symbol metrics, exact candidate
population count, per-job allocated-memory claim, crash-durable span or automatic
retention is introduced. A dashboard client consumes the protected JSON tool.
