# D05 completion receipt

Completed: 2026-11-15 (Europe/Moscow).

Implementation: [`552af00`](https://github.com/resokk/code-crawler/commit/552af00cdfdc4d494b6f0e486495a937f43ff1f1).
Reference-boundary fix: [`470f29f`](https://github.com/resokk/code-crawler/commit/470f29fd3e2025f7175b68231cd0f49ce1e05022).
Final [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43681621831)
succeeded: **1028 passed in 168.30s**, including all migrations, lint, formatting,
integration/regression tests and clean-working-tree checks. Local full final
suite: **1028 passed in 132.53s**.

Acceptance: tests/test_openapi_adapter.py and
tests/integration/test_openapi_storage.py. OpenAPI 3.0/3.1/3.2, recursive/local/
relative/remote/missing/ambiguous refs, discriminator mappings, QUERY/
additionalOperations/querystring, parser budgets, unsafe YAML/paths, data-only
examples/extensions, exact archived Evidence, incremental reuse/edit/delete/
activation, independent repositories, TypeScript config coexistence and failed
producer publication preservation all pass. Existing C01/C02/C03/D02 regressions
pass after integrating concurrent upstream work.

Migration 0025 extends existing UCM symbol/relation registries, without a parallel
graph. Parser operates on captured bytes only; no source execution, network or
external-repository lookup. Coverage remains PARTIAL: dialect syntax and raw
schema facts are retained without effective JSON Schema/runtime interpretation.
Dynamic/base scope is deferred; unsupported extensions have diagnostics.

Full supported versions, safety budgets, mapping and limitations:
docs/openapi-contracts.md. D06 Java bindings remain separate.
The normative proposal, design, specification and completed tasks are preserved.
