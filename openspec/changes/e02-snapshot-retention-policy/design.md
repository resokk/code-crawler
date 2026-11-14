# Design: Pinned snapshot retention and derived data lifecycle

## Context
GC can remove RETIRED snapshots by count; future pinned deployment/query contexts, resolver cache, search generations and blobs need retention rules.

## Decisions
### Decision 1
Define retention classes CURRENT, RETIRED, PINNED, BUILDING/FAILED and minimum preservation periods/explicit pins.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 2
Introduce durable pin references for selected snapshot IDs, explicit owner/use and release/audit workflow.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 3
Make GC mark/sweep across UCM facts, source blobs, search docs, embeddings, discovery and resolver generations without deleting live dependencies.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 4
Support dry-run with planned bytes/entities and safe transaction/retry; no destructive unspecified defaults.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 5
Document rollback after publication and behavior when old snapshots are intentionally expired.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

## Operational lifecycle
Document setup, access scope, preflight checks, dry-run/diagnostics, execution, failure handling, retry, validation and post-action audit. Never hide incomplete status. Preserve ability to read previous publication during in-progress work.

## Security
Secrets only in controlled credentials store/environment; log metadata, not raw private code. Enforce repository ACL for monitoring and restore actions. Tests must use isolated DB fixtures.

## Rollback
Changes that could delete or expose data require dry-run and conservative defaults. Postgres schema updates only through forward migrations; restore evidence and pinned history are acceptance gates.
