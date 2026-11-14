# Capability: backup-restore-validation

## ADDED Requirements

### Requirement: Define backup scope and consistency for PostgreSQL 15 public.ucm_*, ingest_*, search_* and resolver_* plus schema migrations.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Snapshot backed up with dirty-worktree sources
- GIVEN Snapshot backed up with dirty-worktree sources
- WHEN restoring
- THEN exact source evidence fragments match original hashes

### Requirement: Automate restore into a fresh isolated PG15 database with reproducible migration/version verification.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Restore lacks derived embedding cache
- GIVEN Restore lacks derived embedding cache
- WHEN rebuilding projections
- THEN canonical snapshot and reader output remain unchanged

### Requirement: Verify published snapshot pointers, source blob SHA, Evidence fragment roundtrip, Relation/FK and retained version contexts.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Backup interrupted before consistent point
- GIVEN Backup interrupted before consistent point
- WHEN attempting restore
- THEN it fails safely rather than publishing mixed versions

### Requirement: Rebuild derivative search, embeddings/discovery/resolver cache after restore if needed, without changing canonical facts.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Older pinned snapshot and current snapshot
- GIVEN Older pinned snapshot and current snapshot
- WHEN restore completed
- THEN both remain readable and distinguishable

### Requirement: Auditable and reproducible actions
All destructive or publication-related operations MUST be observable, safe under failure, and prevent modification of unrelated repositories.

#### Scenario: Unrelated repository is active
- GIVEN another repository has a published or pinned snapshot
- WHEN this feature operates on one selected repository
- THEN the other repository remains readable and unaffected
