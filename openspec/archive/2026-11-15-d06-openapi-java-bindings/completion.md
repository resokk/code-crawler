# D06 completion receipt

Completed: 2026-11-15 (UTC).

Implementation: [`68c92f4`](https://github.com/resokk/code-crawler/commit/68c92f4969a58c767e2fd1fe8002e13068345916).
[CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43709975173)
succeeded: **1237 passed in 221.52s**. Clean-database migrations, lint, formatting,
unit/integration/regression tests and clean-working-tree checks all succeeded.
The current main descendant also passed [required CI](https://github.com/resokk/code-crawler/actions/runs/43723700838).

Local validation: 1056 passed, 181 PostgreSQL tests skipped without TEST_DATABASE_URL;
108 focused OpenAPI/BPMN/Kafka tests; 27 UCM schema tests; all three D06 PG15
publication/CLI/isolation scenarios passed in 37.61s on the merged implementation.
The earlier full local process had loaded the pre-Kafka-wrapper assertion before
its correction: 1236 passed and that stale assertion failed. The corrected test
passed in the focused PG15 run and the full immutable CI run above.

Acceptance covers class/method paths, original parameter names and dual-source
Evidence, verb mismatch, ambiguous controllers, server/context/media/condition
constraints, constants, inheritance, HEAD priority, missing/invalid Java,
explicit body DTOs and partial parameter associations. Feign targets remain
deferred; dynamic method/URL never invent a concrete selector. Existing canonical
Java CALLS and SQL support operation → handler → service → SQL traversal.

Snapshot tests verify published readback, repeat reuse, edits, ambiguity, context
changes, deletion, preparation failure, historical immutability and no resolution
against another repository. Default CLI preserves Kafka augmentation and exports
both Java catalogs. Canonical Java ASTs and symbol IDs are reused.

Migration 0029 extends existing UCM relation contracts. Discovery projection uses
a locally scoped generic plan for fresh snapshot UUIDs, with caller plan setting
restoration verified during repeated publication. Runtime dispatch/deployment and
serialization remain unproved; HTTP and binding capabilities remain PARTIAL.
Supported subset and limitations: docs/openapi-java-bindings.md.
