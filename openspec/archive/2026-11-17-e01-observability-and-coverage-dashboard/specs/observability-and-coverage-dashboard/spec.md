# Capability: observability-and-coverage-dashboard

## ADDED Requirements

### Requirement: Bounded durable operational observations
The system MUST aggregate fixed stage timing, calls/errors, numeric row and cache
counts and process peak RSS independently of canonical facts. CLI indexing MUST
attach repository, job and attempt. GC totals MUST remain admin-scoped.

#### Scenario: Parallel repositories
- GIVEN two repositories index concurrently
- WHEN their observations are flushed and read
- THEN timings and errors are isolated by repository and job attempt
- AND no source, query or exception strings are stored

#### Scenario: Failed observation write
- GIVEN a published snapshot and an observation insertion failure
- WHEN telemetry is flushed
- THEN its transaction rolls back independently
- AND the canonical publication and source evidence remain available
- AND the original operation exception is not replaced

### Requirement: Protected operational query dashboard
The system MUST require explicit monitor permission and repository membership
before database access. Reports MUST restrict time windows to 1..30 days, support
job filtering and return numeric stage aggregates including P50/P95.

#### Scenario: Read permission alone
- GIVEN an authenticated principal with read but no monitor grant
- WHEN it requests monitoring
- THEN access is denied before DB access without disclosing diagnostics

#### Scenario: Foreign or anonymous client
- GIVEN an anonymous client or a monitor principal outside repository membership
- WHEN it requests privileged diagnostics
- THEN it receives a redacted denial without repository/source information

### Requirement: Published typed coverage
Coverage MUST read one pinned published snapshot. COMPLETE, PARTIAL, UNSUPPORTED
and unknown MUST remain distinct. Ratios MUST use an explicit denominator.
Diagnostics and reasons MUST be reduced to severity and fixed categories.

#### Scenario: Partial SQL analysis
- GIVEN a published index with partial SQL capabilities
- WHEN monitoring is read
- THEN partial counts and categorical reasons are visible
- AND raw paths, source bodies and diagnostic messages are absent

#### Scenario: No publication
- GIVEN a repository with no publication
- WHEN monitoring is read
- THEN coverage reports NO_PUBLICATION instead of a successful zero-error score

### Requirement: Search and cache observations
MCP MUST count returned items/candidates, explicit truncation and resolver HIT/MISS
and collect DB query time without storing query arguments. Stage totals MUST be
aggregated per request before persistence, not retained as unbounded worker state.

#### Scenario: Truncated search
- GIVEN a response exceeds its declared result limit
- WHEN operational metrics are read
- THEN a truncation count and returned-row count are visible without source data

### Requirement: Preserve immutable canonical state
Monitoring MUST NOT alter canonical facts, publication pointers or evidence.

#### Scenario: Unrelated repository remains readable
- GIVEN another repository has a published snapshot
- WHEN metrics fail for one selected repository
- THEN the other publication and its facts remain unchanged
