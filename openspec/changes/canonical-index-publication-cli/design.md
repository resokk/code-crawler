# Design

Add `snapshot validate UUID`, `snapshot publish UUID --expected-current UUID|none`,
and `index-sources --publish`. Delegate lifecycle transitions to validate_snapshot
and publish_snapshot. Manual publication resolves the repository from snapshot
metadata and requires an explicit expected pointer; automatic publication uses the
indexer's base_snapshot_id. Never refresh the expected pointer silently on conflict.

Report snapshot status, entity count, pointer and diagnostic severity counts.
Failures exit nonzero; canonical validation/publication preserve previous visibility.
Use PostgreSQL integration tests for real CLI commands in separate processes,
including invalid snapshots and stale expected pointers. Existing lifecycle tests
remain responsible for low-level locking/concurrent transaction behavior.
