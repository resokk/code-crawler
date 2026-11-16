# Source data security (A06)

Raw archived source and canonical UCM facts remain immutable. Only trusted DB/CLI
code and A02's authorized source reader (`source` grant plus repository membership)
may restore original bytes. MCP structural/Evidence/discovery/traversal responses
and search/embedding projections always apply the built-in mask policy; a source
grant does not disable masking in ordinary MCP responses.

The versioned conservative detector recognizes common credential token prefixes,
private-key blocks (including a truncated block with a recognizable BEGIN header), bearer values, URL credentials and explicit secret/password/
API-key assignments. It does not identify all secrets or personal data: unlabeled
arbitrary values, encoded/fragmented secrets and semantic PII need additional
organization policy. Placeholder references and the redaction marker are excluded.
False positives are possible. Detection never creates canonical facts or upgrades
Certainty/Resolution/Coverage of source analysis.

Projection policy modes: `mask` replaces spans with `[REDACTED]`; `skip` omits the
whole affected document; `reject` aborts the new generation transaction. Defaults
are mask. Safe redaction metadata records policy/version/action, PARTIAL derivative
coverage, field coordinates/category and original UTF-8 byte offsets; no values or
secret fingerprints. Detected values of at least eight characters are masked wherever they occur in
the payload, including provenance, paths and dictionary keys; short explicit
literals are masked only at their detected spans. Canonical IDs and public machine
status/certainty values remain protocol constants. Unlabelled copies of short
values and universal PII recognition are not guaranteed. Budgets
fail closed rather than returning an incompletely scanned document.

C01 retains its additional caller redactor and policy version. Built-in scanning
runs both before and after that callback, which cannot opt out of the baseline.
Callback failures become generic policy errors without their original message.
Projection version changes require a new generation; old unsafe generations are
not served by the current reader. Reject/callback/limit errors leave the previous
published search generation and canonical publication untouched. Masked content
has deterministic hashes. `embedding_input` accepts sanitized content only and
rechecks it; no embedding model or vector store is introduced by A06.

Repository authorization remains mandatory before C01 reads/rebuilds and before
MCP SQL. No global secret corpus or cross-repository redaction cache is retained.
Existing A02 audit uses principal, operation and hashed repository scope, without
query/source values; redaction reports add no plaintext log records.

Retention: search generations/documents/provenance are snapshot derivatives and
are removed by existing snapshot GC; retained resolver contexts and active readers
continue to pin snapshots. Source blobs intentionally outlive links/snapshots until
an explicit retention/GC policy is implemented (E02). A06 does not delete originals
or implement legal erasure, backups, embedding retention or a universal detector.

The bounded profile accepts at most 2 MiB per string, 16 MiB of scanned string
bytes per payload/context, 100000 string fields, depth 64, 256 matches per string
and 4096 findings per scan. A matched span over 64 KiB is rejected before compiling
a replacement expression. Exceeding a budget rejects output without source text
in the error; it never silently returns a partially scanned payload.

Literal replacement uses no secret-bearing regex cache. Replacement work is
bounded by 128 MiB of scanned bytes times known-value count and 4096 occurrences
per payload. Matching corpora are local to a single scan, never shared by tenant.
