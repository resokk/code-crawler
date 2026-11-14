# Design

`ingest_stream(conn, snapshot_id, repository_id, chunks)` consumes an async stream
of entity chunks. Each chunk is rechecked, normalized by the existing `_rows` and
copied to the same temporary staging tables as the batch loader; only that chunk is
held. `_lock_empty`, `_stage` and `_transfer` are shared by both loaders.

Forward references need no ordering: nothing reaches canonical tables until the
stream ends, then deferred foreign keys check every reference. Duplicate IDs fail
on the primary key. Everything is one transaction, so a failing producer, a bad
reference or cancellation leaves an empty BUILDING snapshot that can be retried.

Cross-entity semantic rules of UcmBatch are not evaluated while streaming;
`validate_snapshot` evaluates them before READY, so publication stays gated.
Validation and index_incremental still hold a whole snapshot in memory.
