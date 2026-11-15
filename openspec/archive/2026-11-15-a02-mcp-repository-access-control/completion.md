# A02 completion receipt

Completed: 2026-11-15 (Europe/Moscow).

Implementation after C06 integration: [`7d7e83c`](https://github.com/resokk/code-crawler/commit/7d7e83c2571160b2baff3e3af4d75af41421cf86).

Before integrating the concurrent C06 change, the original A02 boundary passed:
[PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/43735165333)
succeeded: **1252 passed in 165.56s**, including lint/format checks, all migrations
on a clean database and clean-working-tree checks. Final local full suite:
**1252 passed in 290.42s**. Focused authentication/HTTP/PostgreSQL suite: 20 passed.

Acceptance: tests/test_access.py and tests/integration/test_mcp_access.py cover
missing/malformed/expired credentials, malformed/duplicate/wildcard policy,
operation permission distinct from membership, direct unauthenticated tool calls,
source Evidence restoration/denial, forged client claims, two concurrent native
ASGI HTTP identities across every MCP tool, foreign/missing repository redaction,
discovery intersection and DB-error masking. Audit events contain allow/deny and
principal identity without bearer values. Missing-policy startup was additionally
verified to fail before creating the DB pool.

Deployment now requires MCP_ACCESS_POLICY with bearer SHA-256 digests, expiry,
repository memberships and operation grants. No anonymous compatibility mode.
TLS and consistent worker restart for policy changes are operator requirements.
Audit goes to stderr for collection into an access-restricted persistent sink;
a separate durable audit service is not implemented. Raw DB/search/reader APIs
remain privileged administrative interfaces; authorized_evidence is the guarded
library source retrieval entry point. No schema migration, UCM facts or snapshot
writes are introduced. Full boundary and limitations: docs/mcp-access-control.md.

C06 integration: 27 focused auth/HTTP/PostgreSQL/cross-repository tests passed.
The new MCP traversal requires read/discover and authorized server scope for every
context selection plus the root, before DB access. Mixed-repository contexts and
forged snapshot ownership are denied/redacted. Current-head full required CI is
recorded in [PR #8 checks](https://github.com/resokk/code-crawler/pull/8/checks).
