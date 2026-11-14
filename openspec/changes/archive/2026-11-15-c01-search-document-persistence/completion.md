# C01 completion receipt

Completed: 2026-11-15 (Europe/Moscow).

Implementation: [`712018b`](https://github.com/resokk/code-crawler/commit/712018b668f4c86e68e2712a43eebf764fedf06c).
[CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43649003961)
succeeded, including all migrations, lint, formatting, integration/regression
tests and clean-working-tree checks. Local full suite after upstream rebase:
**927 passed in 135.01s**.

Acceptance evidence: tests/test_search_storage.py and
tests/integration/test_search_document_storage.py. Stable hashes/identity,
atomic generations, SQL failure/cancellation/policy rollback, concurrent CAS,
repository/snapshot scope and denied access, pinned reads, ORM/SQL/symbol
provenance, uncertainty, full/incremental reuse, empty generations and GC pass.
The historical-schema query benchmark regression also passes.

API, fields, versioning and compatibility: docs/search-documents.md.
Authorization and secret redaction are mandatory trusted-caller inputs; HTTP ACL
and the full A06 policy are separate changes. Reindex is explicit; embeddings
and automatic indexing integration are deferred. B02 remains open: projection
still materializes the snapshot and makes no bounded-memory/scale claim.

The proposal, design, specification and completed tasks are preserved here.
