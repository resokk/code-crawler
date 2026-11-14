# Proposal: Pinned snapshot retention and derived data lifecycle

## Why
GC can remove RETIRED snapshots by count; future pinned deployment/query contexts, resolver cache, search generations and blobs need retention rules.

## Goal
Bring code-crawler to production readiness without changing canonical UCM semantics.

## Scope
- Define retention classes CURRENT, RETIRED, PINNED, BUILDING/FAILED and minimum preservation periods/explicit pins.
- Introduce durable pin references for selected snapshot IDs, explicit owner/use and release/audit workflow.
- Make GC mark/sweep across UCM facts, source blobs, search docs, embeddings, discovery and resolver generations without deleting live dependencies.
- Support dry-run with planned bytes/entities and safe transaction/retry; no destructive unspecified defaults.
- Document rollback after publication and behavior when old snapshots are intentionally expired.

## Non-goals
- Do not change UCM entities, SQL relations or cross-repository resolution without explicit evidence.
- No new infrastructure or privileged access by default; require operator approval for destructive operations.

## Dependencies
Requires stable canonical snapshots, repository ACL, ingestion jobs and published reader. Run in parallel with adapters where possible.

## Impact
src/code_crawler/ and docs/ as relevant, tests/integration/ and PostgreSQL migrations if the data model changes.
