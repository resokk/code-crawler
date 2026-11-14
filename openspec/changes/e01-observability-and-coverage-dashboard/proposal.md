# Proposal: Ingestion, search and analysis coverage observability

## Why
Existing ingest stages and diagnostics are distributed across logs, snapshots and source reports; no central operational view for hundreds of repositories.

## Goal
Bring code-crawler to production readiness without changing canonical UCM semantics.

## Scope
- Instrument analyze/prepare/stage/transfer/FK/validate/publish and GC durations plus RSS, rows, retries and errors per repo/job.
- Expose per-adapter parsed files, diagnostics, unsupported constructs and Coverage ratios without treating unknown as failure.
- Measure MCP search P50/P95, DB query timing, candidate counts, truncation and resolver cache hit/miss.
- Design redacted operational dashboard/query API scoped by role/workspace and repository; avoid exposing source bodies.
- Define cardinality limits and aggregation for metrics to avoid per-symbol high-cardinality time series.

## Non-goals
- Do not change UCM entities, SQL relations or cross-repository resolution without explicit evidence.
- No new infrastructure or privileged access by default; require operator approval for destructive operations.

## Dependencies
Requires stable canonical snapshots, repository ACL, ingestion jobs and published reader. Run in parallel with adapters where possible.

## Impact
src/code_crawler/ and docs/ as relevant, tests/integration/ and PostgreSQL migrations if the data model changes.
