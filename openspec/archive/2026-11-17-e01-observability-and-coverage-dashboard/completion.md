# E01 completion receipt

Implementation: [`00be481`](https://github.com/resokk/code-crawler/commit/00be481851c8ccdd091826102f6f8e67bc0206b4).
[Required PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/44022374709)
succeeded: **1382 passed in 221.28s**, all migrations, lint/format and working-tree
checks passed. Local mandatory PG15 full suite: 1382 passed in 414.36s. Final
focused CLI/MCP/ACL/metrics suite: 34 passed; updated PG lock-failure/evidence
acceptance test: 1 passed. PR: https://github.com/resokk/code-crawler/pull/16.

Acceptance: tests/test_observability.py checks bounded numeric counters, independent
concurrent tasks, error preservation and window validation. tests/test_server.py
checks explicit monitor permission and repository membership before DB access.
HTTP two-principal tests include monitoring and foreign-snapshot redaction.
tests/integration/test_operational_metrics.py builds and publishes two concurrent
Java repositories, reads partial SQL coverage and categorical reasons, verifies
latencies/counters/retries/job isolation, no-publication state, and injects both
a metrics-table lock timeout and a rejected insert. Canonical publication pointers
and exact archived source bytes remain readable after those failures.

Delivered: migration 0031 operational observations, fixed stage collectors,
CLI job/attempt and global admin-only GC observations, MCP query/cache/DB counters,
get_monitoring with explicit monitor grant, numeric percentiles, bounded published
adapter/capability coverage and redacted diagnostic categories.

Limits: process peak RSS is not per-job allocation; stage totals are nested;
search timing excludes transport/pool/redaction; candidates count returned items;
unreported capabilities remain unknown; GC is not attributed to individual repos;
unfinished/crashed observations can be lost; retention is operator-managed.
No web UI or monitoring infrastructure is added. Setup, DB grants, timeout behavior,
security boundaries and contracts: docs/observability.md. PR remains unmerged.
