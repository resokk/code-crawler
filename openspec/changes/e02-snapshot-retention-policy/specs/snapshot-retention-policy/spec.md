# Capability: snapshot-retention-policy

## ADDED Requirements

### Requirement: Define retention classes CURRENT, RETIRED, PINNED, BUILDING/FAILED and minimum preservation periods/explicit pins.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Retired snapshot pinned by deployment context
- GIVEN Retired snapshot pinned by deployment context
- WHEN running GC
- THEN pinned snapshot and evidence remain intact

### Requirement: Introduce durable pin references for selected snapshot IDs, explicit owner/use and release/audit workflow.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Two snapshots share source blob
- GIVEN Two snapshots share source blob
- WHEN deleting one snapshot
- THEN shared blob remains available to the other

### Requirement: Make GC mark/sweep across UCM facts, source blobs, search docs, embeddings, discovery and resolver generations without deleting live dependencies.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Snapshot has no live references
- GIVEN Snapshot has no live references
- WHEN retention expires
- THEN facts and only truly orphan derived resources are removed

### Requirement: Support dry-run with planned bytes/entities and safe transaction/retry; no destructive unspecified defaults.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: GC preview invoked
- GIVEN GC preview invoked
- WHEN printing plan
- THEN nothing is deleted until explicit approval/execution

### Requirement: Auditable and reproducible actions
All destructive or publication-related operations MUST be observable, safe under failure, and prevent modification of unrelated repositories.

#### Scenario: Unrelated repository is active
- GIVEN another repository has a published or pinned snapshot
- WHEN this feature operates on one selected repository
- THEN the other repository remains readable and unaffected
