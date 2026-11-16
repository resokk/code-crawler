# Completion: A03 database-qualified structural search

Implementation: `234635a4224879921c241fa5ad8d7fef570c56a8`.

SQL readers/writers preserve default SYNTACTIC_NAME lookup and add explicit
RESOLVED_DATABASE_OBJECT retrieval by database/version/table or snapshot-local
DATABASE_OBJECT ID. Exact results require stored RESOLVED bindings matching the
published snapshot, database context, schema version and fingerprint. Identifier
spelling is preserved; all file projections of the same physical object match.
Unassigned, PARTIAL, AMBIGUOUS and UNRESOLVED accesses remain excluded with explicit
coverage. Physical resolution never establishes execution; A04 statuses and all
original access, sink and relation evidence remain visible. Shared SQL execution
sinks are restricted to the selected contextual access.

Acceptance covers two databases and schema versions, quoted identifiers, readers
and writers, uncertain bindings, object-ID conflicts/foreign IDs, pagination,
repeatable-read publication isolation, repository ACL and generic MCP errors.
Search writes no facts or publication pointers; analyzers are unchanged.

Migration 0030 adds the physical-object composite index. Fixed 3,010-object PG15
EXPLAIN ANALYZE BUFFERS comparisons preserve results and reduce object lookup
shared-buffer hits from 36 to 3. The [captured plans](../../../docs/benchmarks/database-qualified-search-pg15.json)
record workload, baseline SHA, platform, timings and memory/buffer details.
Single warm samples are plan evidence, not a throughput or latency guarantee.

Validation:

- Ruff lint and format checks: passed.
- Local mandatory PostgreSQL 15 full suite: 1284 passed in 280.10s.
- Combined A03/A04 focused suite: 33 passed; strengthened proof regression: 1 passed.
- [PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/43863262370):
  success, 1284 passed in 230.50s on the implementation SHA above; clean-database
  migrations and working-tree checks passed.

Only current published snapshots are searched; object IDs are snapshot-local.
Global db: keys are provenance, not selectors. No implicit latest schema version
or guessed binding is introduced. See the [search contract](../../../docs/structural-search.md).
