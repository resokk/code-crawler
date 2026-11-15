# Streaming ingestion

## Requirement: chunked load with forward references

GIVEN a valid set of entities streamed one per chunk in any order WHEN the stream
ends THEN all entities are stored and the count is returned.

## Requirement: atomicity under faults

GIVEN a producer error, a dangling reference, a duplicate ID, an entity of another
repository, or cancellation mid-stream WHEN loading THEN the call fails, the
snapshot has no entities, no staging tables remain, and a retry into the same
snapshot succeeds.

GIVEN a non-empty snapshot WHEN a stream is loaded THEN it is rejected.

## Requirement: bounded memory

GIVEN streams of 4 000 and 16 000 entities in equal chunks WHEN loaded THEN peak
loader memory for the larger stream is below 1.5 times the smaller one.

## Requirement: publication gate preserved

GIVEN a streamed snapshot WHEN it is validated THEN the full UcmBatch rules apply
before it can become READY.

## Requirement: validation without the whole snapshot in memory

GIVEN a valid stored snapshot WHEN it is validated in slices of any size THEN it
becomes READY with the same entity count as the whole-batch validator accepts.

GIVEN a stored snapshot the whole-batch validator rejects WHEN it is validated in
slices THEN it is rejected too and stays VALIDATING without a receipt.

GIVEN snapshots of 4 000 and 16 000 entities WHEN validated THEN peak validator
memory for the larger one is below 1.5 times the smaller one.
