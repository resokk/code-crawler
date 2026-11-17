# Proposal: A07 — migration history integrity and SQL schema resolution

## Problem

Between `main@b5b3f35` and `main@e133ccc`, the historical migration files `0003`–`0029` were edited to remove explicit `public.` qualification. Existing populated databases do not rerun already applied migrations. The migration runner `src/code_crawler/db.py` stores only file `name` and `applied_at`, not a checksum, and uses PostgreSQL's session `search_path` implicitly. A fresh PG15 init passes CI, but it does not prove compatibility of a database migrated with the earlier SQL.

Two distinct migration filenames use the prefix `0030_`. This is accepted by current lexicographic filename order, but strict order/rollback expectations have not been established for already applied databases.

This change is about verification and future safety. It is **not evidence that an existing database is corrupted**.

## Goals
- Safely upgrade a populated PG15 database created from the old migration set, preserving immutable snapshots, publication pointers, archived Evidence, searches and grants.
- Detect accidental changes to future applied SQL migration content, while supporting an explicit audited handling procedure for already deployed historical files.
- Specify schema selection (`public` vs explicitly configured schema), consistent `search_path` for migrations and runtime SQL, and protection from wrong-schema object lookup.
- Make branch-merge migration order deterministic and auditable; avoid silent application of a previously inserted migration out of chronological order.

## In scope
1. Pre-change populated PostgreSQL 15 upgrade fixture and repeatable regression tests.
2. Persistent migration identity/fingerprint manifest with a non-destructive transitional policy for historical migrations.
3. Schema/search_path contract and tests with non-default role search_path and similarly named objects in two schemas.
4. Migration ordering/duplicate-number validation and documented recovery path.
5. New **forward-only** migration(s) if absolutely required; no edited historical SQL replays.

## Out of scope
- Automatic schema relocation or rewriting existing UCM tables from public into another schema.
- In-place changes to historical migration files, drop/recreate, or changing canonical UCM entity/SQL semantics.
- Claiming a universal rollback path for arbitrary manual DBA operations.

## Dependencies
No product feature dependency; tests require PostgreSQL 15 and historical `b5b3f35` migration fixture. Coordinate with A05 CI protection.

## Code surface
`src/code_crawler/db.py`, `src/code_crawler/migrations/` (new files only), `tests/test_db.py`, `tests/integration/test_postgres.py`, `docs/db.md`, `.github/workflows/ci.yml`.

## Rollout
Start in report-only mode for legacy installs whose applied hashes were never saved. No automatic trust or destructive repair. Establish an operator-approved one-time baseline tied to a known historical migration release; only then enforce immutable content for subsequent migrations.
