# Tasks: Ingestion, search and analysis coverage observability

- [ ] 1. Review current docs and migration/observability or retention implementations; reproduce missing behavior.
- [ ] 2. Define minimal interfaces and durable typed contracts.
- [ ] 3. Implement: Instrument analyze/prepare/stage/transfer/FK/validate/publish and GC durations plus RSS, rows, retries and errors per repo/job.
- [ ] 4. Implement: Expose per-adapter parsed files, diagnostics, unsupported constructs and Coverage ratios without treating unknown as failure.
- [ ] 5. Implement: Measure MCP search P50/P95, DB query timing, candidate counts, truncation and resolver cache hit/miss.
- [ ] 6. Implement: Design redacted operational dashboard/query API scoped by role/workspace and repository; avoid exposing source bodies.
- [ ] 7. Implement: Define cardinality limits and aggregation for metrics to avoid per-symbol high-cardinality time series.
- [ ] 8. Add positive and negative acceptance test: Index job finishes with partial SQL coverage / reading monitoring metrics / partial coverage and its reasons are visible
- [ ] 9. Add positive and negative acceptance test: Two repositories index in parallel / viewing metrics / each job/repository has independent stage latency and error count
- [ ] 10. Add positive and negative acceptance test: MCP queries exceed response limit / viewing dashboards / truncated counts are visible without source content
- [ ] 11. Add positive and negative acceptance test: Anonymous monitoring client / requesting privileged diagnostics / source paths/secrets are not exposed
- [ ] 12. Verify snapshot pointer immutability and evidence availability after failure/recovery.
- [ ] 13. Add PostgreSQL 15 integration or operator runbook validation when relevant.
- [ ] 14. Document constraints, security boundaries and explicit Coverage.
- [ ] 15. Run ruff, pytest --require-postgres, CI and failure-injection suite; archive only after all checks pass.
