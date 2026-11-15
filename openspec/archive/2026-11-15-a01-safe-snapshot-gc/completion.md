# A01 completion receipt

Completed: 2026-11-15.

Implementation: [`7066de3`](https://github.com/resokk/code-crawler/commit/7066de3047e227722529666fa25c8ec9170cca63).
[PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/43684599884)
succeeded: **1112 passed in 128.51s**, with lint, formatting, clean-database
migrations and clean-working-tree checks. Local full suite: 1111 passed; the
subsequently added selected-reader lease case passed with all 18 final GC tests.

Acceptance covers managed table ownership, unrelated snapshot_id tables,
unknown/pending migrations, missing managed tables, unsafe/inbound FKs,
inheritance, transactional rollback/redacted diagnostics, state/publication
protection, reader leases, active jobs, cancellation and migration coordination.
Current-main search generation cascades are counted correctly; existing saved
resolver context/deployment retention tests also pass. Historical benchmarks use
only their disposable database and explicit trial UUID.

No migrations or new UCM facts. Existing public report keys are retained with
additive counts/skips/diagnostics. GC remains row-based; large-snapshot performance
and retention scheduling remain separate changes. Direct SQL readers must opt
into snapshot leases; unrecognized inbound FKs stop cleanup rather than extending
its deletion scope. Full behavior: docs/ingest-jobs.md.
