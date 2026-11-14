# Ingest jobs

## Requirement: persistent job state

GIVEN an index run WHEN it succeeds THEN its job is SUCCEEDED with its stage,
attempt and snapshot ID.

GIVEN an adapter failure WHEN the run ends THEN the job is FAILED at stage INDEX
with the error type, message and per-file diagnostics, and no snapshot is published.

## Requirement: safe retry

GIVEN a FAILED job WHEN retried THEN a new attempt runs with the stored parameters,
attempt increments and the previous failure is cleared.

GIVEN a job running in another process WHEN retried THEN the command exits nonzero
without changing the job.

GIVEN a SUCCEEDED job WHEN retried THEN the command exits nonzero.

GIVEN a RUNNING job whose process is gone WHEN GC runs THEN it becomes FAILED.

## Requirement: controlled cleanup and retention

GIVEN a BUILDING snapshot older than the threshold with no running job in its
repository WHEN GC runs THEN the snapshot and all its facts are deleted.

GIVEN more RETIRED snapshots than `--keep-retired` WHEN GC runs THEN only the
oldest excess ones are deleted; the PUBLISHED snapshot and kept versions remain
intact and indexing continues to work.

GIVEN no GC flag WHEN facts of a RETIRED snapshot are deleted directly THEN the
database rejects it.

GIVEN `snapshot gc` without options WHEN parsed THEN it exits nonzero and deletes
nothing.
