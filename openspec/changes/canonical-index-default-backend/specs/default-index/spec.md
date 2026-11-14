# Default canonical indexing

## Requirement: canonical standard flow

### Scenario: default local index
GIVEN a local Git repository WHEN index runs without --backend THEN it produces and
publishes validated archived UCM readable by canonical API, without legacy rows.

### Scenario: remote clone and update
GIVEN a remote repository WHEN indexed/reindexed THEN the correct identity-qualified
clone is created/updated using fast-forward only and the resulting UCM is published.

### Scenario: source identity
GIVEN different sources with the same basename WHEN indexed without explicit keys
THEN they do not share canonical repository identity or remote cache by basename.

### Scenario: repeat and failure
GIVEN a publication WHEN unchanged sources are indexed THEN canonical facts reuse
is preserved; WHEN parsing/validation/publication fails THEN old publication remains
selected and legacy is not used as fallback.

## Requirement: explicit legacy compatibility

### Scenario: explicit legacy index
GIVEN --backend legacy WHEN index runs THEN the old writer is used with an explicit
SQL-discovery warning, without creating canonical execution claims.

### Scenario: migration of unused SQL
GIVEN a legacy SQL literal with executes WHEN migrated THEN those compatibility
edges are not promoted to confirmed canonical SQL execution relations.

### Scenario: option validation
GIVEN legacy backend plus canonical-only options WHEN index runs THEN it fails
before source/DB mutation rather than silently ignoring those options.
