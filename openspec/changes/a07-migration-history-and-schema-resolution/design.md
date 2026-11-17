# Design: A07 — database migration upgrade safety

## Observed baseline

`db.migration_names()` lexicographically sorts filenames; `schema_migrations` contains only `(name, applied_at)`; `db.schema_state()` compares sets of names; `db.apply_migration()` reads current on-disk SQL and inserts its name after execution. `db.connect()` does not fix the session schema. Historical SQL had `public.` qualifiers, while current files mostly do not. The main CI creates clean PG15 databases and cannot reveal upgrades of preexisting populated DBs.

## Decision 1 — reproduce real upgrade before changing migration machinery

- Create a dedicated historical fixture using exactly the pinned old source tree/migrations at `b5b3f35`, including one published snapshot and source archive, derived search data and a retained context when available.
- Upgrade using current migration runner from the latest main; never use a production database or rewrite/rollback the historical files to force success.
- Before/after compare table/schema locations, PK/FK/index/trigger inventory, migration names, publication pointer, Evidence bytes SHA, read/search results and no-snapshot-mixing.
- Test a fresh database on the current schema in parallel and produce a machine-readable diff of structural equivalence (ignoring expected new migration tables/columns).
- Failure must be explicit and leave the pre-upgrade clone recoverable.

## Decision 2 — immutable migration identity with legacy reconciliation

- Consider a forward-compatible `schema_migrations` extension (`sha256`, optionally SQL artifact/release identifier) via a new numbered migration/bootstrap path.
- Record checksum **before application** and validate it on subsequent `db migrate/status`; never silently update stored checksum to current on-disk content.
- For legacy names with no historical checksum, build an allowlisted manifest of verified old/new code revisions and require operator approval or known deployment provenance to set baseline; mark unknown provenance `UNVERIFIED`, not `MATCHED`.
- If a previously applied migration hash differs, block new migrations by default and surface filename, expected/actual hash and safe repair instructions without SQL/credential leakage.
- Decide whether migration IDs are full filenames (current model) or numeric-prefix constraints. Do not mislabel two distinct 0030 names as already a physical DB error; test the real upgrade order.

## Decision 3 — schema resolution is explicit

- Product owner must choose an explicit supported policy: fixed `public` or configured schema. Document it; do not silently infer from default search_path.
- Set/verify the intended schema resolution for `db init`, `db migrate`, `db status` and application connections in one consistent mechanism (safe explicit qualification or known `search_path`).
- For non-default role search_path and duplicate object names in a second schema, tests verify UCM operations hit only the selected schema or fail closed.
- The `schema_migrations` metadata table is also subject to the same schema policy; prevent shadowing/unknown status caused by another table with that name.
- Do not create a parallel accidental UCM in `public` or another schema just to make tests pass.

## Decision 4 — rollout and observability

- Add CI integration tests for a full old-data upgrade, fresh install and malicious/ambiguous search_path settings.
- Preserve existing already published snapshots and their immutable facts, plus no-change indexing and reader/GC behavior.
- Provide `db status --verify` or equivalent report with migration identity, historical provenance, current schema OIDs and unmatched state; do not auto-approve.
- Document the operator procedure for legacy reconciliation and rollback from a database backup. Make it clear a check cannot retroactively prove SQL originally applied without a stored checksum.

## Risks

- SHA of a historical *file in current Git* is not proof it was used for a long-lived database. Never backfill this without provenance or user approval.
- Locking/checksum changes must not block routine fresh migration test environments or violate one-migration-per-transaction atomicity.
- PostgreSQL `search_path` includes temporary/user schemas; qualification or controlled setting must avoid unpredictable object shadowing.
- A future schema policy must not create raw SQL injection via schema identifiers (validate/quote identifiers).
- A schema relocation is a separate explicitly approved project, not part of A07.
