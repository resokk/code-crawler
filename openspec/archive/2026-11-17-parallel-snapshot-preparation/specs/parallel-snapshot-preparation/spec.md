# Capability: parallel-snapshot-preparation

## ADDED Requirements

### Requirement: Explicit bounded workers
CLI MUST accept integer analysis-workers 1..32, default 1, and persist it for retry.
Parallel mode MUST keep at most one in-flight group per worker within a source slice.

#### Scenario: Invalid setting
- GIVEN zero, negative, boolean or over-cap workers
- WHEN configuration is validated
- THEN execution is rejected before preparation/publication

### Requirement: Consistent isolated CPU analysis
Workers MUST use captured bytes and matching catalogue/settings versions. AST and
DB resources MUST NOT be transferred. Facts/order MUST match sequential analysis.

#### Scenario: Matching workers
- GIVEN the same captured inventory and profile
- WHEN 1, 2 or 4 workers analyze it
- THEN complete facts, dependencies, coverage and metadata observations match

#### Scenario: Catalogue mismatch
- GIVEN a child builds a different analysis version
- WHEN initialization is checked
- THEN preparation fails before canonical write/publication

### Requirement: Safe resource lifecycle
Worker death, errors and cancellation MUST abort preparation, release processes
and preserve the previous publication. PostgreSQL writes MUST remain in the parent.

#### Scenario: Abrupt worker death
- GIVEN a worker terminates during a request
- WHEN the parent waits for its result
- THEN it detects failure without waiting indefinitely and terminates the group

#### Scenario: Incremental reuse
- GIVEN unchanged sources and only a different worker count
- WHEN indexing runs again
- THEN facts remain reusable and no child pool is needed

### Requirement: Reproducible scaling evidence
Measurements MUST compare 1/2/4 workers with complete fact digests, runtime and
summed parent/child memory, reporting startup/catalogue replication limitations.

#### Scenario: Small workload
- GIVEN startup cost exceeds available parallel work
- WHEN measurements show slower preparation or larger memory
- THEN the regression is recorded and default remains 1
