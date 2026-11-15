# Completion: C03 repository version contexts

Immutable typed selection manifests cover latest, exact pinned and explicit deployment
versions. Saved contexts and deployment mappings retain snapshots until release.
GC and pin changes share transaction coordination; all reads require explicit grants.

Contract: [resolver-contexts.md](../../../../docs/resolver-contexts.md).
PG15 acceptance includes concurrent publication, foreign/BUILDING snapshot rejection,
latest fingerprint change, immutable saved selections, denied access, deployment
uncertainty and retention after both kinds of pin release.

Validation: ruff check/format and full PostgreSQL 15 suite: 932 passed.
