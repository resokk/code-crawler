# Completion: C05 resolver cache and invalidation

Added PostgreSQL derivative cache migration, exact request/version keys, TTL and
FIFO capacity limits, payload size/digest/scope/uncertainty validation, dependency
cascades, safe-GC integration and read-only cache use by C04. CLI warms/prunes; no
canonical graph or published ExternalReference is mutated by a cache request.

Contract: [resolver-cache.md](../../../docs/resolver-cache.md).
Coverage and request provenance are retained on hits. Missing/corrupt/expired caches
recompute C04; unavailable generations bypass entries. Publication creates different
latest-context keys, while pinned/deployment contexts retain their own identity.

PostgreSQL acceptance includes concurrent warming, a generation race, rollback,
GC/active reader leases, unavailable storage, denied access and forged confidence.
On the fixed fixture miss/hit SQL round trips are 33/10; JUnit records both counts.

Validation: ruff check/format and full mandatory PostgreSQL 15 suite: 1180 passed.
The integrated baseline includes safe-GC preflight/leases, resolver unknown-type
handling, sliced canonical validation and D07 Kafka message facts. Cache storage
uses migration 0028 after Kafka migration 0027.
