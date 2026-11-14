# Source evidence

## Requirement: exact archived bytes

### Scenario: dirty checkout disappears
GIVEN tracked dirty source bytes WHEN indexed and published and checkout is deleted
THEN its Evidence fragment is restored byte-for-byte with hash/dirty/fingerprint provenance.

### Scenario: clean source and reuse
GIVEN a clean source snapshot WHEN published and reindexed unchanged THEN both
snapshots have complete links and share the repository/content hash blob.

### Scenario: missing or forged bytes
GIVEN SourceFiles without complete matching archived bytes WHEN validation or direct
publication is attempted THEN it fails and the current pointer is unchanged.

### Scenario: ingest failure
GIVEN an archive or facts write failure WHEN indexing runs THEN partial facts/links
are rolled back and existing publication remains selected.

## Requirement: scoped verified retrieval

### Scenario: wrong snapshot or repository
GIVEN archived bytes WHEN read under another repository or unpublished snapshot
THEN no bytes are returned and the request fails explicitly.

### Scenario: invalid ranges or integrity failure
GIVEN non-boundary/out-of-bounds SourceRange or content hash mismatch WHEN reading
THEN retrieval fails without returning a misleading fragment.

## Requirement: immutable historical compatibility

### Scenario: upgrade an existing publication
GIVEN a PUBLISHED/RETIRED snapshot predating migration WHEN upgraded THEN its facts
and pointer remain intact, rollback still works, and unavailable bytes are explicit.

### Scenario: archive mutation
GIVEN frozen snapshot links and blobs WHEN update/delete/truncate is attempted
THEN it is rejected, and a new snapshot cannot acquire a legacy exemption.
