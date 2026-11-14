# Completion: C02 global discovery catalog

Implemented versioned normalized catalog projections, publication/rollback atomicity,
bounded authorized lookup, missing-generation reporting and GC cascades. Unsupported
HTTP/Kafka/worker/dataset declarations remain explicit rather than inferred from clients.

Normative API and coverage: [discovery-catalog.md](../../../../docs/discovery-catalog.md).
PostgreSQL acceptance: tests/integration/test_discovery_catalog.py.

Validation: ruff check/format and full PostgreSQL 15 suite: 929 passed.

## Scoped read API and sealing extension

Preserved the concurrently published C02/C03 JSON-key schema, library lookup API
and snapshot retention pins. Forward migration 0026 adds generation sealing and
an identifier lookup index; projector discovery/2 adds full database qualifiers
and BPMN targetNamespace precision. Added read-only MCP, explicit server grants,
coherent manifests, generation-aware pagination and CLI refresh.

Extended contract: docs/global-discovery-catalog.md.
Validation against integrated C01/C02/C03 and D02/D11 main: **1024 passed** with
PostgreSQL 15; ruff check and format check passed. Tests cover the original
catalog/context contracts plus denied access, ordered signatures, immutability,
MVCC/pagination, failure/rollback/GC and C01 generation coexistence.

OpenAPI integration preserves root-path operation declarations as PARTIAL HTTP
contract candidates under explicit contract IDs, with unknown runtime service
identity. Document titles, servers, callbacks and webhooks do not become service
bindings/endpoints. Verified with the extended catalog fixtures, 912 unit tests
and 24 publication/OpenAPI/BPMN/GC integration tests on PostgreSQL 15.
