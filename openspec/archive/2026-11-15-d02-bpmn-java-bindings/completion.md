# D02 completion receipt

Completed: 2026-11-15 (Europe/Moscow).

Implementation:
[`970a736`](https://github.com/resokk/code-crawler/commit/970a7368405078fc59a92e7c55a3eb1f1e0c9f1d).
Required [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43650283341)
succeeded: **997 passed**, no skipped tests, in 153.66 seconds. Locked dependency
installation, lint, formatting, all clean-database migrations and clean-working-tree
checks succeeded. The local full PG15 suite also passed all 997 tests.

The implementation was rebased on `2b787a1` to preserve D10/D11 source adapters
and C01/C02/C03 publication/discovery/version-context behavior. Forward migration
is `0024_bpmn_java_bindings.sql`; it adds typed relation registry entries only.

Acceptance:
- Unique compatible delegate/Spring bean/worker links to canonical Java methods
  with BPMN and Java Evidence; ambiguous beans retain both candidates.
- Camunda 7/8 and Flowable 6/7 profiles are explicit and versioned. Dynamic,
  unsupported and remote-only selectors remain deferred.
- Process-variable reads/writes and XML mappings are typed facts; name-based
  lineage remains PARTIAL/AMBIGUOUS and INFERRED.
- Existing reader/trace composes BPMN_HANDLER with Java EXECUTES_SQL. The BPMN
  adapter creates no SQL execution facts or duplicate Java/SQL analyzers.
- Publish/read/reuse, candidate addition/removal, bean rename, profile changes,
  deletion, preparation failure and remote-repository isolation are tested.
- Typed immutable catalogs reuse the canonical Java AST, validate captured source
  provenance/ranges and avoid catalog construction in non-BPMN projects.

Tests: `tests/test_bpmn_java_bindings.py`, `tests/test_adapter_catalogs.py`,
`tests/integration/test_bpmn_java_storage.py`; runtime limitations and supported
APIs are documented in `docs/bpmn-java-bindings.md`.

Proposal, design, normative specification and checked tasks are preserved here.
Runtime registration, expression evaluation and confirmed variable data lineage
remain outside the proven static subset; binding Coverage remains PARTIAL.
