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

Validation is streamed too. The UcmBatch rules are plain functions shared by the
batch model and `validate_snapshot`, which applies them to slices of 2 000 entities
in entity_id order. Referenced entities are read on demand into a bounded cache;
row totals per table replace the whole-snapshot "unconsumed rows" check. Only the
cross-entity SQL rules see more than a slice: they receive every SQL fact of the
snapshot. Porting those rules to SQL is change b02.
