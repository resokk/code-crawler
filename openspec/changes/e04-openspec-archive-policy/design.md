# Design: Persistent OpenSpec history and change dependencies

## Context
Completed changes were removed from active openspec/changes; Git history alone does not provide browsable rationale for subsequent LLM tasks.

## Decisions
### Decision 1
Define active openspec/changes versus completed openspec/changes/archive and a stable naming convention.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 2
After implementation + CI + acceptance, archive proposal/design/specs/tasks with completion receipt and commit/CI link.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 3
Maintain roadmap with dependencies, current baseline SHA, priority and explicit open criteria.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 4
Provide agent execution instructions: implement one change at a time, do not invent new capabilities, preserve tests/docs, stop at scope boundary.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

### Decision 5
Handle superseded specs by linking replacements and archiving instead of deleting evidence of design decisions.

Implementation must expose diagnostics, remain idempotent and preserve historical version pins. Treat canonical UCM and archived evidence as immutable source of truth; derived state can be rebuilt with explicit versioning.

## Operational lifecycle
Document setup, access scope, preflight checks, dry-run/diagnostics, execution, failure handling, retry, validation and post-action audit. Never hide incomplete status. Preserve ability to read previous publication during in-progress work.

## Security
Secrets only in controlled credentials store/environment; log metadata, not raw private code. Enforce repository ACL for monitoring and restore actions. Tests must use isolated DB fixtures.

## Rollback
Changes that could delete or expose data require dry-run and conservative defaults. Postgres schema updates only through forward migrations; restore evidence and pinned history are acceptance gates.
