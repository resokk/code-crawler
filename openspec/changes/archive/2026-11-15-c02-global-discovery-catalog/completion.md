# Completion: C02 global discovery catalog

Implemented versioned normalized catalog projections, publication/rollback atomicity,
bounded authorized lookup, missing-generation reporting and GC cascades. Unsupported
HTTP/Kafka/worker/dataset declarations remain explicit rather than inferred from clients.

Normative API and coverage: [discovery-catalog.md](../../../../docs/discovery-catalog.md).
PostgreSQL acceptance: tests/integration/test_discovery_catalog.py.

Validation: ruff check/format and full PostgreSQL 15 suite: 929 passed.
