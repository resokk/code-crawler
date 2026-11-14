# Design: Ingestion, search and analysis coverage observability

## Context
Existing ingest stages and diagnostics are distributed across logs, snapshots and source reports; no central operational view for hundreds of repositories.

## Decisions
### Decision 1
Instrument analyze/prepare/stage/transfer/FK/validate/publish and GC durations plus RSS, rows, retries and errors per repo/job.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 2
Expose per-adapter parsed files, diagnostics, unsupported constructs and Coverage ratios without treating unknown as failure.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 3
Measure MCP search P50/P95, DB query timing, candidate counts, truncation and resolver cache hit/miss.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 4
Design redacted operational dashboard/query API scoped by role/workspace and repository; avoid exposing source bodies.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 5
Define cardinality limits and aggregation for metrics to avoid per-symbol high-cardinality time series.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

## Operational lifecycle
Document setup, access scope, preflight checks, dry-run/diagnostics, execution, failure handling, retry, validation and post-action audit. Never hide incomplete status. Preserve ability to read previous publication during in-progress work.

## Security
Secrets only in controlled credentials store/environment; log metadata, not raw private code. Enforce repository ACL for monitoring and restore actions. Tests must use isolated DB fixtures.

## Rollback
Changes that could delete or expose data require dry-run and conservative defaults. Postgres schema updates only through forward migrations; restore evidence and pinned history are acceptance gates.
