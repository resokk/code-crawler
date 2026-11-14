# Design

A read-only repeatable-read context selects the repository publication once. Bounded
queries hydrate selected canonical IDs using existing publication document decoding,
then validate Entity models. No full-snapshot UcmBatch load for entity/page reads.
Incoming relations include candidates. Evidence reads use existing archive verifier;
only a typed historical-unavailable exception may yield an explicitly partial proof.

The reader lifetime is bounded by the context/connection, with no process session
cache. Concurrent publication and GC do not change its MVCC view. Existing MCP
read transactions use repeatable-read; search output contracts stay unchanged.
