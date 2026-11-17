# Capability: java-sql-flow-copy-on-write

## ADDED Requirements

### Requirement: Lazy isolated branch state
SQL forks MUST share binding graphs until a write. A writing branch MUST preserve
aliases within its graph and MUST NOT mutate siblings or saved outer scopes.

#### Scenario: Read-only branch
- GIVEN a flow forks into branches that do not change tracked bindings
- WHEN those branches are traversed
- THEN variable/value graph copies are not required

#### Scenario: Nested mutation
- GIVEN branches sharing builder values or saved shadowed bindings
- WHEN one assigns, appends, changes partial state or consumes a dirty value
- THEN the write occurs on a detached graph and siblings retain their prior state

### Requirement: Preserve recovery semantics and bounds
The change MUST preserve complete fact payloads, provenance, partial reasons,
path order and the existing limit. It MUST NOT prune branches based on literals.

#### Scenario: No-literal assignment
- GIVEN a branch assigns a constant, parameter or alias without a string literal
- WHEN SQL is recovered after the branch
- THEN its fact payload matches eager recovery

#### Scenario: Truncated paths
- GIVEN nested forks exceed the configured path budget
- WHEN recovery runs with lazy or eager copies
- THEN candidates, constructions and truncation reasons match exactly

### Requirement: Reproducible performance evidence
A controlled benchmark MUST compare the same corpus and budget with complete
fact digests and report timing, process RSS and copy counts with environment data.

#### Scenario: Write-heavy workload
- GIVEN the fixed benchmark corpus contains tracked mutations
- WHEN current main and copy-on-write are measured
- THEN any speed or memory regression is reported along with fact equivalence
