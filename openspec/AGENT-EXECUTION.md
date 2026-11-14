# Agent execution guide — OpenSpec

1. Read `AGENTS.md`, `docs/development-plan-v2.md`, this roadmap, then choose exactly **one** unsatisfied change whose dependencies are ready.
2. Read its proposal.md, design.md, specs/<capability>/spec.md and tasks.md in that order; compare with actual current code before editing. If behavior is already implemented, add missing tests/documentation and record evidence rather than reimplementing.
3. Keep changes local to the feature. Use Python 3.12+ and existing libraries; only permitted PostgreSQL extensions, all schema changes through new numbered SQL migrations in public.
4. Preserve immutable snapshot lifecycle, atomic publication and repository-level isolation. Remote links remain deferred; query-time resolver is derivative. Never promote an unresolved or inferred relationship to STATIC_PROVEN without evidence.
5. Create deterministic fixtures for positive and negative scenarios, including malformed inputs, ambiguous targets, missing external repos, rollback and partial Coverage. Test both full and incremental indexing when relevant.
6. Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` and PostgreSQL 15 tests using `--require-postgres` where storage is involved. Benchmark performance features with a fixed workload and report SHA, host and memory/latency/IO metrics.
7. Update the associated docs, migration notes, and tasks.md only after verification. Existing incomplete `openspec/changes/*` must not be silently archived or altered.
8. Commit and push the completed change on the designated implementation branch, keeping one logical feature per change. Archive the completed spec preserving acceptance evidence. Do not merge to main without the configured required CI.

## Review checklist
- Does it add a false SQL execute or confirmed cross-repo relation?
- Can other repositories, current publications or source bytes be modified unexpectedly?
- Could untrusted parser input trigger network, filesystem escapes or code execution?
- Could search/embedding/MCP expose a repository or secret without ACL?
- Are version, context, Evidence and partial/ambiguous statuses retained?
- Is a failed transaction atomic, and is retry safe?
