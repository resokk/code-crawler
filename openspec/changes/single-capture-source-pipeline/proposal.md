# Single capture source pipeline

Every tracked file was read three times per run: before adapter preparation, again
inside index_incremental and again for the final change check. Capture once, pass
the inventory between preparation and indexing, and keep detecting source changes
until analysis completes. The public adapter contract does not change.
