# Tasks

- [x] Document archive policy, provenance, upgrade behavior and acceptance scenarios.
- [x] Add migration for immutable checked blobs/links and historical compatibility.
- [x] Archive captured bytes atomically in incremental and legacy ingest.
- [x] Require complete archives at validation/publication, including SQL guard.
- [x] Add hash-verified scoped SourceRange retrieval and CLI provenance/status.
- [x] Test recovery after checkout deletion, reuse, dirty sources, integrity/ranges, rollback and upgrade on PostgreSQL 15.
- [x] Full PostgreSQL 15 suite: 800 passed; Ruff/format/diff checks pass; docs updated.
- [x] Hosted CI run after push (CI/PostgreSQL 15 workflow added by mandatory-postgres-ci).

- [x] Rebased on origin/main with R2/search/MCP: 817 full-suite tests pass; 6 archive/GC integration tests and clean migrations pass. Source archive migration is 0017.

Verified by [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43612670068) at `e8e5f18` (842 tests passed).
