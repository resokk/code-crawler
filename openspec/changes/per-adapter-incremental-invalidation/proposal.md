# Per-adapter incremental invalidation

One combined registry fingerprint forced every language to be re-analyzed when any
adapter or its catalog changed. Store each adapter's version and fingerprint with
the snapshot and invalidate only the changed adapter's files plus their dependents.
One published snapshot still covers all adapters.
