# Design

`search_documents.project(entities)` is a pure function over the entities of one
snapshot, yielding `SearchDocument`. It indexes data accesses, EXECUTES_STATEMENT
and CALLS relations once, then emits documents in entity-ID order with sorted
lines, so output does not depend on input order.

Projection is generic over adapters: any Symbol or SqlStatement is projected and
tagged with the language of its source file, which covers Groovy and PL/Plus
without per-language code. Parameters and locals are omitted.

Documents restate facts: relations carry their certainty, unresolved calls are
counted with their reason and never named, and an SQL statement without an
execution relation says so. `id` is derived from kind and entity ID;
`content_sha256` covers title and text for later embedding caching.
