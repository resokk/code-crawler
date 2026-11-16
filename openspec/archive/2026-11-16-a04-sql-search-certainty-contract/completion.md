# Completion: A04 SQL search certainty contract

Implementation: `aeea02fdb08e953fac0e11fc14e8923bd19409f4`.

Read-only SQL search now separates discovery, static execution linkage and DB
resolution. The additive `SqlSearchStatus` contract preserves previous arguments
and response fields. SQL without a sink remains visible with NOT_ESTABLISHED;
INFERRED canonical links retain their certainty. Access, sink and statement
relations include original Evidence/Coverage/resolution. Unresolved statement
relations remain visible even when statements is empty, with explicit PARTIAL
coverage explaining missing SQL or unresolved candidate links.

Acceptance fixture covers an unused DELETE literal, concatenated SQL passed to
prepareStatement, a sink with unknown SQL, unresolved DB identity, MCP DTO
compatibility and unchanged canonical relation counts. Existing snapshot, access
control, input validation and read-only regressions also passed.

Validation:

- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- Local mandatory PG15 full suite: 1261 passed; final targeted SQL/MCP suite: 5 passed.
- [PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/43859377294):
  success, 1261 passed in 284.13s on the implementation SHA above; clean-database
  migrations and working-tree checks passed.

No schema migration or stored UCM semantics changed. A03 DB-qualified retrieval
remains a separate change. Static linkage is not evidence of runtime execution.
See [structural search contract](../../../docs/structural-search.md).
