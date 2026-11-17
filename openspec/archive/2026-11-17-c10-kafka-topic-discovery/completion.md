# Completion: C10 Kafka topic discovery

Implementation: `7c2204f29093df9ad23e555dc01173bd8a48c266` (shared C10/C11 projector upgrade).

Baseline: D07 stored typed NewTopic/send/listener facts and JSON resource selectors,
but C02/C04 reported Kafka target declarations as UNSUPPORTED. Discovery/3 now
projects only static KAFKA_TOPIC Symbols reached by KAFKA_DECLARES_TOPIC from
KAFKA_DECLARATION with the exact Apache NewTopic API. Producers, consumers,
subscriptions, dynamic topics and client configuration alone do not define targets.
No D07 canonical facts or historical migrations are changed for C10.

The C02 JSON key is `[topic]`, with optional cluster/environment qualifiers and
existing snapshot/generation/entity/range provenance. The KAFKA alias remains;
KAFKA_TOPIC is also accepted by the MCP tool. C04 resolver/3 validates existing D07
JSON selectors, removes the repository-local site suffix from cross-repository
lookup, and constrains each known cluster/environment exactly. Malformed identities
and runtime expressions have no static lookup key. Unknown context permits
multiple candidates; even a unique contextual match remains PARTIAL. No physical
topic existence, deployment, delivery or cross-repository canonical edge is proved.

C03 selected snapshots/retention leases and C05 generation/algorithm cache keys
remain authoritative. New publications do not change pinned older snapshot facts.
Latest-context lookup after rename cannot reuse a cached old declaration; an
explicit old context still reads its retained version. Refresh is deterministic
and atomic: cancellation after generation replacement rolls back to the old one.
Projector-version supersession retains the existing C03 unavailable-generation
contract; it does not silently fall back to latest. Existing D07 snapshots can be
refreshed without reparsing; worker canonical additions in the shared migration
are specific to C11.

CI tested `0b8b5e250fe1b73a5dd488f672fef24bd9fb8fdf`, a documentation-only
descendant containing the exact implementation above.

Validation:

- Local complete mandatory PG15 suite: 1509 passed (437.10 s); the final added
  Camunda 7 case was checked separately with all new resource/selector cases:
  34 passed. Ruff check, format check and git diff check passed.
- CI: 1510 passed; clean PostgreSQL 15 migrations, lint/format and generated
  file/working-tree checks passed.
- https://github.com/resokk/code-crawler/actions/runs/44181302582
- Synthetic source/target/other repositories cover send-only exclusion, dynamic
  declaration exclusion, unknown-cluster ambiguity, exact cluster/environment
  filtering, bounded fanout, missing grants, cache reuse, rename, pinned reads,
  deterministic refresh, publication rollback and cancelled projection rollback.
- No performance claim or unrelated optimization is included.

Contracts and operational limits: [global-discovery-catalog.md](../../../docs/global-discovery-catalog.md),
[external-reference-candidates.md](../../../docs/external-reference-candidates.md),
[kafka-message-intelligence.md](../../../docs/kafka-message-intelligence.md).
