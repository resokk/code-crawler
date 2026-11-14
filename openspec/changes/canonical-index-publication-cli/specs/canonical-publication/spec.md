# Canonical publication

## Requirement: explicit validation

GIVEN a valid BUILDING snapshot WHEN `snapshot validate` runs THEN it becomes READY,
entity count and diagnostics are reported, and publication does not change.

GIVEN invalid stored facts WHEN validation runs THEN the CLI exits nonzero and the
current published snapshot remains selected.

## Requirement: expected-pointer publication

GIVEN a valid snapshot and the expected current pointer WHEN `snapshot publish`
runs THEN it validates as needed and atomically selects PUBLISHED.

GIVEN a stale expected pointer WHEN publication runs THEN the CLI exits nonzero,
the concurrent publication remains selected, and target data remain intact.

GIVEN a current PUBLISHED target and matching expected pointer WHEN published again
THEN the operation succeeds without changing its content or visibility.

GIVEN malformed UUIDs or missing expected-current WHEN parsing CLI arguments THEN
usage fails before database mutation.

## Requirement: optional automatic publication

GIVEN source input WHEN `index-sources --publish` succeeds THEN the resulting
snapshot is validated and published using its base pointer, with status/counts.

GIVEN the same sources without --publish WHEN indexing succeeds THEN the new
snapshot remains BUILDING and current publication does not change.

GIVEN publication failure after indexing WHEN --publish is requested THEN exit is
nonzero and the previous publication pointer is preserved.
