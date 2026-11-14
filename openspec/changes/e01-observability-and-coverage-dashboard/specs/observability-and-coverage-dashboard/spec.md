# Capability: observability-and-coverage-dashboard

## ADDED Requirements

### Requirement: Instrument analyze/prepare/stage/transfer/FK/validate/publish and GC durations plus RSS, rows, retries and errors per repo/job.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Index job finishes with partial SQL coverage
- GIVEN Index job finishes with partial SQL coverage
- WHEN reading monitoring metrics
- THEN partial coverage and its reasons are visible

### Requirement: Expose per-adapter parsed files, diagnostics, unsupported constructs and Coverage ratios without treating unknown as failure.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Two repositories index in parallel
- GIVEN Two repositories index in parallel
- WHEN viewing metrics
- THEN each job/repository has independent stage latency and error count

### Requirement: Measure MCP search P50/P95, DB query timing, candidate counts, truncation and resolver cache hit/miss.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: MCP queries exceed response limit
- GIVEN MCP queries exceed response limit
- WHEN viewing dashboards
- THEN truncated counts are visible without source content

### Requirement: Design redacted operational dashboard/query API scoped by role/workspace and repository; avoid exposing source bodies.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Anonymous monitoring client
- GIVEN Anonymous monitoring client
- WHEN requesting privileged diagnostics
- THEN source paths/secrets are not exposed

### Requirement: Auditable and reproducible actions
All destructive or publication-related operations MUST be observable, safe under failure, and prevent modification of unrelated repositories.

#### Scenario: Unrelated repository is active
- GIVEN another repository has a published or pinned snapshot
- WHEN this feature operates on one selected repository
- THEN the other repository remains readable and unaffected
