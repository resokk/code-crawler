# Design: Backup and restore of PostgreSQL UCM and source evidence

## Context
No verified disaster-recovery procedure covers canonical UCM snapshots together with content-addressed source blobs and derived search indices.

## Decisions
### Decision 1
Define backup scope and consistency for PostgreSQL 15 public.ucm_*, ingest_*, search_* and resolver_* plus schema migrations.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 2
Automate restore into a fresh isolated PG15 database with reproducible migration/version verification.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 3
Verify published snapshot pointers, source blob SHA, Evidence fragment roundtrip, Relation/FK and retained version contexts.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 4
Rebuild derivative search, embeddings/discovery/resolver cache after restore if needed, without changing canonical facts.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 5
Measure recovery time/backup size and document operator runbook; never use production credentials in tests.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

## Operational lifecycle
Document setup, access scope, preflight checks, dry-run/diagnostics, execution, failure handling, retry, validation and post-action audit. Never hide incomplete status. Preserve ability to read previous publication during in-progress work.

## Security
Secrets only in controlled credentials store/environment; log metadata, not raw private code. Enforce repository ACL for monitoring and restore actions. Tests must use isolated DB fixtures.

## Rollback
Changes that could delete or expose data require dry-run and conservative defaults. Postgres schema updates only through forward migrations; restore evidence and pinned history are acceptance gates.
