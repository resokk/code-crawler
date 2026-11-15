# D12 completion receipt

Completed: 2026-11-15 (Europe/Moscow).

Implementation: [`c541510`](https://github.com/resokk/code-crawler/commit/c541510bc6d64237a4f84c8fd4d696f86173dddf).
[CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43683088998)
succeeded: **1094 passed in 161.08s**, including all migrations, lint,
formatting, integration/regression tests and clean-working-tree checks.
Local full suite before final upstream integration: 1059 passed; final focused
VBScript suite: 31 passed. ANTLR 4.13.2 regeneration is byte-identical.

Acceptance: tests/test_vbscript_ucm.py and
tests/integration/test_vbscript_adapter.py cover case-insensitive symbols,
classes/properties/parameters/scopes, local versus deferred calls, SQL candidates
without execution, tracked ADODB sinks, dynamic/unknown/shadowed receivers,
UTF-8 byte ranges, archived source Evidence, malformed and bounded input,
publication rollback, incremental reuse/edit/delete and adapter-version invalidation.

Uses captured source bytes, existing UCM facts and snapshot lifecycle. No schema
migration, source execution, COM activation or external lookup is introduced.
Coverage remains PARTIAL: the bounded grammar and file-local flow analysis do
not implement host includes, runtime dispatch, interprocedural value recovery,
or ADO parameter lineage. Unsupported behavior and conservative invalidation
are documented in docs/vbscript-ucm.md.

The normative proposal, design, specification and completed tasks are preserved.
