# Proposal: Backup and restore of PostgreSQL UCM and source evidence

## Why
No verified disaster-recovery procedure covers canonical UCM snapshots together with content-addressed source blobs and derived search indices.

## Goal
Bring code-crawler to production readiness without changing canonical UCM semantics.

## Scope
- Define backup scope and consistency for PostgreSQL 15 public.ucm_*, ingest_*, search_* and resolver_* plus schema migrations.
- Automate restore into a fresh isolated PG15 database with reproducible migration/version verification.
- Verify published snapshot pointers, source blob SHA, Evidence fragment roundtrip, Relation/FK and retained version contexts.
- Rebuild derivative search, embeddings/discovery/resolver cache after restore if needed, without changing canonical facts.
- Measure recovery time/backup size and document operator runbook; never use production credentials in tests.

## Non-goals
- Do not change UCM entities, SQL relations or cross-repository resolution without explicit evidence.
- No new infrastructure or privileged access by default; require operator approval for destructive operations.

## Dependencies
Requires stable canonical snapshots, repository ACL, ingestion jobs and published reader. Run in parallel with adapters where possible.

## Impact
src/code_crawler/ and docs/ as relevant, tests/integration/ and PostgreSQL migrations if the data model changes.
