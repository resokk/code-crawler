# Proposal: Persistent OpenSpec history and change dependencies

## Why
Completed changes were removed from active openspec/changes; Git history alone does not provide browsable rationale for subsequent LLM tasks.

## Goal
Bring code-crawler to production readiness without changing canonical UCM semantics.

## Scope
- Define active openspec/changes versus completed openspec/archive and a stable naming convention.
- After implementation + CI + acceptance, archive proposal/design/specs/tasks with completion receipt and commit/CI link.
- Maintain roadmap with dependencies, current baseline SHA, priority and explicit open criteria.
- Provide agent execution instructions: implement one change at a time, do not invent new capabilities, preserve tests/docs, stop at scope boundary.
- Handle superseded specs by linking replacements and archiving instead of deleting evidence of design decisions.

## Non-goals
- Do not change UCM entities, SQL relations or cross-repository resolution without explicit evidence.
- No new infrastructure or privileged access by default; require operator approval for destructive operations.

## Dependencies
Requires stable canonical snapshots, repository ACL, ingestion jobs and published reader. Run in parallel with adapters where possible.

## Impact
src/code_crawler/ and docs/ as relevant, tests/integration/ and PostgreSQL migrations if the data model changes.
