# Design

Use repository-scoped content-addressed PostgreSQL blobs, immutable snapshot/file
links, SHA-256 checks in SQL and Python, and provenance origin. Store bytes in the
existing atomic ingest transaction for incremental and legacy capture. Generic
producers supply SourceInput explicitly before validation. Publication requires full
archive coverage; a SQL trigger backs the Python check. Migration grandfathering
is restricted to snapshots already PUBLISHED/RETIRED and cannot be expanded later.

Read fragments by repository + frozen snapshot + SourceRange, never by local path.
Validate full-file SHA and UTF-8 byte boundaries before slicing. Reuse existing
SourceFile identity and snapshot metadata; add no adapter dependencies on storage.
Previously published data remain immutable and readable with explicit unavailable
status where bytes were never retained. Retention/GC and permissions are separate.
