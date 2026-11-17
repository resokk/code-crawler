# Design

A thread-local slot owns a bounded cache during a synchronous file operation.
Root decorators establish it inside java.analyze, Java symbol extraction and all
Java per-file analysis entry points. Nested same-thread helper calls reuse the
scope; no await occurs inside it. Each file in a 64-file worker slice gets a new
scope. ThreadPool worker reuse and asyncio.to_thread context propagation do not
share the slot between threads. finally clears all Node/text references and
restores the prior slot, including exceptions. Cancelled to_thread workers finish
their synchronous operation and clean up in that worker.

Keys are retained Node handles rather than naked node.id integers. Their tree
remains alive, so unrelated or newly parsed trees cannot reuse a cached address.
This also safely handles references to other catalogue trees during one file's
analysis. The cache never survives that operation. Empty strings use a dedicated
miss sentinel; None preserves the original empty return. Decoding remains UTF-8
with errors=replace. Outside a scope the helper decodes directly.

Fixed limits: 8192 entries and 1 MiB of decoded-string storage measured with
sys.getsizeof. Above a limit, decode without admission; do not evict/reinsert on
hot paths. Node handles/dict overhead are additionally bounded by the entry cap.
Counters contain only hit/miss/admission/peak byte counts, not source content.
The private synchronous scope must not span awaits or a multi-file worker loop.

Validate fresh keys/text for successive files, retained-tree identity, empty/None,
UTF-8 replacement, cleanup on failure, nested helpers and simultaneous worker
threads. Compare entire parse/UCM payloads with uncached decoding across Java
profiles and path truncation. Benchmark fixed fresh-process corpora with time,
RSS, source/fixture hashes and hit counters. A small share of profile time is
not a guaranteed end-to-end speedup.
