# Capability: java-sql-path-budget-report

## ADDED Requirements

### Requirement: Per-analysis configurable budget
Java SQL recovery MUST default to 256 retained paths and accept integer budgets
1..65536 without process-global mutation. Every SQL-derived profile MUST honor it.

#### Scenario: Concurrent settings
- GIVEN two analyzers with different budgets
- WHEN both recover the same branching method concurrently
- THEN each retains its own bounded states and truncation reasons

#### Scenario: Invalid budget
- GIVEN zero, a negative, boolean, non-integer or an over-cap budget
- WHEN configuration is validated
- THEN it is rejected before analysis or publication

### Requirement: Explicit overflow diagnostics
An optional JSONL report MUST identify methods/constructors whose recovery pruned
states, including those with no SQL candidate. Exactly reaching a budget MUST NOT
be reported as overflow. Counts MUST distinguish lower bounds from exact totals.

#### Scenario: Overflow with no SQL
- GIVEN a method exceeds its path budget without constructing SQL
- WHEN reporting is enabled
- THEN a metadata-only case identifies its file, hash, owner and coordinates

#### Scenario: Exact boundary
- GIVEN a method produces exactly its configured number of states
- WHEN no states are pruned
- THEN no overflow case is emitted

### Requirement: Incremental identity and report scope
Budget changes MUST invalidate Java reuse. Diagnostic destinations MUST NOT alter
facts. Reports MUST explicitly cover only reanalyzed methods, including reuse counts.

#### Scenario: Reused files
- GIVEN unchanged files are reused
- WHEN a report is requested
- THEN its summary states the limited scope and does not claim a complete repository census

### Requirement: Safe report lifecycle
Reports MUST be private, atomically replaced and exported before publication.
Failure export MUST preserve the original analysis error. Retry MUST retain settings.

#### Scenario: Report export failure
- GIVEN a new BUILDING snapshot and an unwritable report destination
- WHEN report export fails
- THEN the prior publication pointer remains unchanged

#### Scenario: Failed analysis
- GIVEN some method cases were observed before analysis failed
- WHEN the report can be exported
- THEN it has FAILED status and partial observations without source/SQL bodies
