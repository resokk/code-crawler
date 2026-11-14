# D01 completion receipt

Completed: 2026-11-15 (Europe/Moscow).

Implementation commit:
[`b70b6f7`](https://github.com/resokk/code-crawler/commit/b70b6f78e152d76c03765e97c07e5f3a6b1bab36).
Required [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43646257264)
succeeded: **882 tests passed** in 119.18 seconds, including integration tests;
all migrations, lint, formatting and clean-working-tree checks passed.

Conformance: `tests/test_bpmn_adapter.py` (22 tests) and
`tests/integration/test_bpmn_storage.py` (publish/read/reuse/edit/delete,
repository isolation, deferred remote process, producer-failure preservation).
The adapter uses captured bytes only; DTD/XXE and implicit UTF-16 are rejected.

The normative proposal, design, specification and checked tasks are preserved
in this directory. Supported mapping and limitations: `docs/bpmn-schema.md`.
Coverage intentionally remains PARTIAL: XML facts and explicit references are
preserved; expressions/extensions are not executed, XSD/engine runtime semantics
are not asserted. Java bindings remain D02.
