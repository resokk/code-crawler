# Source capture

## Requirement: sources are read once per run

GIVEN an unchanged worktree WHEN a source index run prepares adapters, analyzes and
verifies THEN each tracked file is read from disk exactly once.

## Requirement: changes during indexing are detected

GIVEN a file whose content changes, or which is deleted, after capture WHEN the run
reaches verification THEN it fails with "worktree changed during analysis" and no
snapshot is created.

GIVEN a file whose timestamps change but whose bytes do not WHEN verified THEN only
that file is re-read and the run continues.

GIVEN HEAD, branch, dirty state or the tracked file list changes WHEN verified THEN
the run fails.
