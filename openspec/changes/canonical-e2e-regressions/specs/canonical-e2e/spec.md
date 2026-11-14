# Canonical e2e

## Requirement: full published pipeline

### Scenario: mixed repository
GIVEN Java/Groovy/PLPlus sources WHEN indexed/validated/published/read THEN canonical
calls, SQL constructions, execution sites, table accesses and exact Evidence exist
in one snapshot with preserved Coverage.

### Scenario: unused SQL
GIVEN an unused SQL literal WHEN the pipeline runs THEN its construction is present
but no confirmed execution is attributed to it.

### Scenario: repeat indexing
GIVEN unchanged sources WHEN indexed again THEN facts are reusable and reader
results are equivalent, scoped to the new published snapshot.

### Scenario: publication rollback
GIVEN an existing publication WHEN publication of a new valid snapshot fails THEN
old pointer/state and canonical reader facts remain intact.
