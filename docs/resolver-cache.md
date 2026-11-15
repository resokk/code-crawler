# Resolver cache (C05)

C04 resolution remains authoritative over immutable UCM/discovery facts. The cache
is a disposable PostgreSQL derivative; deleting it changes performance, not results.
The existing `search.resolve_external_reference` API and CandidateResolution schema
are unchanged. Queries automatically read a compatible cache entry, or compute C04.

## Read-only lifecycle

MCP stays read-only and stateless. Only CLI/maintenance code warms or prunes the
cache. A miss never writes from a request. Authorization and C03 context verification
happen before every cache lookup, including hits. A missing cache table, absent /
expired / corrupt entry or incompatible payload falls back to C04. Missing catalog
generations bypass the cache; no old RESOLVED result can hide partial availability.

Key version `resolver.cache/1` includes selector/hints hash, immutable source
repository/snapshot/reference identity, source descriptor digest, context fingerprint,
selected generations digest, discovery projector version, resolver algorithm version
and candidate limit. Mode, deployment services and versions are already part of the
context fingerprint. Identical selectors at different callsites do not share source
Evidence. New latest selections miss old keys; explicit retained contexts can still
use their own entries. Rollback can reuse an unexpired entry for the exact old context.

Cache hits validate SHA-256, the typed response, source/origin identity, reference
certainty/coverage and every candidate/Evidence scope against the verified context.
They preserve uncertainty and never create canonical Relations. Warm accepts a
request, never an arbitrary result supplied by a client, and always recomputes C04.

## Limits, expiry and races

TTL defaults to 300 seconds (allowed 1..3600). At most 1000 entries are retained,
with a maximum 256 KiB UTF-8 response per entry and at most 32 dependency rows.
Expired/oldest-write entries are removed during warming or explicit prune. Hits do
not update recency: eviction is FIFO by write time, not an in-memory LRU.
Oversized results are returned normally but are not stored. Small negative and
partial results may be cached with their original reasons and provenance.

Reads, generation verification and C04 computation share one read-only REPEATABLE
READ transaction. Transaction-scoped snapshot leases also protect cache hits from
concurrent GC and are released with the request. Warming computes in such a read, then revalidates versions before
an atomic write. Snapshot/generation key-share locks and the GC/cache transaction
locks prevent insertion against disappearing dependencies. A generation race skips
the write rather than storing a result under a newer version. Dependency cascades
remove entries on snapshot GC or catalog-generation deletion. Both cache tables
are explicitly listed before their parents in the safe GC registry; their `snapshot_id`
identifies the source owner (entries) or selected dependency (dependency rows). Caches do not retain
snapshots. Cache loss is harmless and requires no canonical rebuild.

`code_crawler.resolver_cache` emits structured INFO events `cache_status=HIT|MISS|BYPASS`
with a bounded reason and opaque key/context hashes. No selector, source text or raw
Evidence is logged. Log aggregation supplies hit/miss instrumentation without
process-global counters or writes from read-only requests.

## Maintenance

```sh
uv run code-crawler resolver-cache warm context.json org/app ucm:REFERENCE_ID --limit 50 --ttl-seconds 300
uv run code-crawler resolver-cache prune
```

The manifest file is the C03 `ResolverContext.model_dump_json()` representation.
CLI is an administrative DB client and derives the explicit scope from this typed
manifest; public services must obtain grants from authorization, not from a user's
manifest. Library APIs `warm_resolver_cache` and `prune_resolver_cache` likewise
require a free connection; warming additionally requires trusted repository grants.
The migration contains all DDL; no cache state is kept in a worker session.

## Verification

PostgreSQL fixtures cover freshness after publication, pinned/deployment isolation,
rollback, GC and generation cascades, a generation switch between compute/write,
concurrent capacity enforcement, TTL, malformed and scope-inconsistent payloads,
false certainty promotion, oversized results and an absent cache schema. CLI warm /
prune are exercised against the same DB. The two-repository fixture uses 33 SQL
calls for a miss and 10 for a hit (including active snapshot leases); this is a
round-trip comparison, not a general latency guarantee. JUnit properties record
`cache_miss_queries` and `cache_hit_queries`.
