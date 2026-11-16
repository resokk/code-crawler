# A06 completion receipt

Implementation: [`e73b25d`](https://github.com/resokk/code-crawler/commit/e73b25d3cffde946a6704b08782ecb7f8d01c189).
[Required PostgreSQL 15 CI](https://github.com/resokk/code-crawler/actions/runs/43864176148)
succeeded: **1305 passed in 283.47s**, including Ruff, formatting, every migration
on a clean DB and clean-working-tree checks. Local full suite before final A03
integration: 1280 passed; final targeted policy/auth/projection/PG suite: 50 passed.

Acceptance: tests/test_data_security.py and
tests/integration/test_source_data_security.py verify explicit/prefixed credentials,
private keys including truncated blocks, short literals, false positives,
UTF-8 coordinates, nested provenance/keys, deterministic masked hashes, source
context after caller callbacks, generic callback failures, canonical IDs and
machine certainty, resource bounds, raw-source integrity after checkout deletion,
authorized source versus denied access, masked MCP/embedding input, generation
mask/skip/reject, legacy-reader rejection, immutable reports and snapshot GC.
Existing C01/A02/A03/A04 regressions pass in the full suite.

Migration 0030 adds immutable generation security_report. Projection v2 requires
rebuilding legacy derivatives; original sealed generations, canonical facts and
publication/source hashes are never rewritten. Reports and documents are removed
with their owning generation/snapshot. Raw source blob retention remains E02.

This is a conservative bounded detector, not universal secret/PII discovery.
Unlabelled/encoded/fragmented values and short unlabelled copies are not guaranteed.
Canonical IDs and public machine constants are preserved; actual raw evidence
requires A02 source grant plus membership. Raw DB/CLI APIs remain privileged.
No embedding model or vector retention service is introduced. Full detector and
limits: docs/source-data-security.md; final head validation: PR #10 checks.
