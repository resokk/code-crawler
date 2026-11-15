# Global discovery catalog (C02)

Derived `search_discovery_generations` and `search_discovery_entries` are built
atomically inside canonical publication, including rollback. Every entry retains
repository/snapshot/generation, canonical entity, selector-specific JSON key,
qualifier and source range. Equal names in different repositories remain separate.
Publication failure rolls back the generation and pointer together. Retired entries
remain available for pinned version contexts; ordinary lookup joins current pointers.
Snapshot GC explicitly lists both derivative tables in its allowlist and deletes only
its own derivative rows. Foreign-key cascades additionally prevent orphans. Generation identity includes
projector version and snapshot ID; refresh never rewrites canonical facts.

Supported projections: exact case-sensitive Symbol FQN, callable FQN plus ordered
parameter types (unknown signature differs from zero arguments), full database
identity (database/schema version/catalog/schema/object kind/table/column), explicit
BPMN process IDs from canonical BPMN_ATTRIBUTE facts. Connection aliases, HTTP
clients and worker subscriptions are not declarations of remote targets. OpenAPI operations under root paths produce PARTIAL HTTP contract candidates with
explicit contract ID and null service identity. Runtime HTTP bindings are not
inferred from document titles, servers or repository names. Callback/webhook targets,
Kafka topic/worker and dataset declarations are not invented from external references.
Kafka/worker/dataset coverage remains UNSUPPORTED.

`discovery.lookup` accepts an explicit bounded set of authorized repository keys.
Empty/absent authorization denies access before querying. Limit is 1..200; lookup
fetches limit+1 and reports truncation. Results are candidates, never code edges or
proof of invocation. Keys are compared exactly; a hash expression index narrows
lookup, with full JSON equality protecting against collisions. Reads are stateless.
Compound reads require a caller-owned read-only REPEATABLE READ transaction.
`refresh_discovery` is a CLI/maintenance API for already-published snapshots, including
backfill after upgrade; it does not load a complete UCM graph or source checkout.

Migration 0026 and projector discovery/2 add sealed-generation guards, full DB
qualifiers and BPMN targetNamespace precision, preserving the existing JSON-key
schema and C03 generation contract. The read-only MCP and identifier-oriented API,
explicit server allowlist, coherent manifests and fingerprint pagination are
specified in [global-discovery-catalog.md](global-discovery-catalog.md).


Discovery publication scopes generic planning to its declaration projection: fresh
snapshot IDs absent from statistics can otherwise get pathological custom join
plans after repeated publication. The caller's plan_cache_mode is restored within
a savepoint; projection identities and sealed generation semantics are unchanged.
