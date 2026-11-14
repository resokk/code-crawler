# Design

`AnalysisScope(key, analysis_version, fingerprint, suffixes)` describes one adapter;
the fingerprint is SHA-256 of its descriptor manifest and prepared catalog version.
Migration 0015 adds `ingest_snapshot_adapters`, immutable with the snapshot facts.

When the combined profile differs and the baseline has scope rows, files routed to
scopes with a different or missing fingerprint become invalidation seeds; the usual
reverse transitive closure over file dependencies (explicit and entity references,
across languages) then selects dependents. Facts of other files are reused.

A baseline without scope rows (older snapshot, or built without scopes) is rebuilt
in full: nothing proves its facts current. Route changes are covered by the file
language being part of the file fingerprint.
