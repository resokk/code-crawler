# Tasks

- [x] Document policy, stable check name, diagnostics and acceptance scenarios.
- [x] Add PostgreSQL 15 service workflow with locked Python environment and migrations.
- [x] Enforce mandatory pytest DB/selection/no-skips while preserving local opt-in runs.
- [x] Check working-tree drift and upload failure artifacts.
- [x] Verify policy with isolated positive/negative pytest sessions.
- [x] Local mandatory suite: 809 passed, zero JUnit skips/failures; Ruff/format, actionlint 1.7.7 and isolated clean/tracked/untracked drift checks pass.
- [ ] Hosted GitHub Actions run after push.
- [ ] Enable/verify required check in main branch rules (repository settings).

- [x] Rebased on origin/main with R2/search/MCP: 817 full-suite tests pass; 6 archive/GC integration tests and clean migrations pass. Source archive migration is 0017.
