# Completion: C04 external reference candidate search

Implemented read-only bounded lookup within C03 manifests against C02 catalog
versions. Results retain per-candidate repository/snapshot/generation, source and
target Evidence paths, certainty, coverage, rules and explicit resolution status.
Canonical ExternalReference and Relations are not changed.

Contract: [external-reference-candidates.md](../../../../docs/external-reference-candidates.md).
Public backend API: search.resolve_external_reference. Principal-aware MCP exposure
remains A02/C09. No resolver cache or storage migration is introduced in C04.

Acceptance includes unique exact signature, ambiguous/missing targets, partial source
certainty, unknown signature/version, denied access, wrong source snapshot, unavailable
generation, absent target source range, rollback/pinned versions and bounded output
from 1001 declarations. DB fixtures prove full identity separation and reject an
identical connection alias in a different origin file. Kafka/worker target producers absent from the current UCM remain explicitly
UNSUPPORTED. D05 OpenAPI operations are projected by discovery/2 and retrieved as
HTTP contract candidates only within compatible explicit deployment service mappings.
They retain PARTIAL certainty until canonical service/implementation binding exists.

Validation on the integrated D02/D05/sealed-catalog baseline: ruff check/format
and full PostgreSQL 15 suite: 1062 passed.
