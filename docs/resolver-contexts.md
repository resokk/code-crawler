# Repository version contexts (C03)

`resolver_context.select_context` returns an immutable typed manifest, selected
repository/snapshot/catalog generation/commit IDs and a SHA-256 fingerprint. One
repository has exactly one selected snapshot. Inputs are an explicit bounded set
of repository keys and a trusted allowlist; denied access never triggers target
lookup or source access. No global process cache or implicit repository scan exists.

Modes:

- LATEST_INDEXED selects current published pointers in one read-only REPEATABLE READ
  transaction. A new call recomputes latest; an already-returned manifest stays fixed.
- PINNED_SNAPSHOTS requires exact repository/snapshot ownership and PUBLISHED or
  retained RETIRED state. BUILDING/READY/foreign/missing snapshots are errors.
- DEPLOYMENT_CONTEXT requires an explicitly registered immutable deployment key,
  with service→repository/snapshot bindings covering all requested repositories.
  Unknown/incomplete mappings are errors; there is no latest fallback.

Catalog absence is explicit (`generation=None`); `verify_context` reports missing
or superseded generations. Identity/ownership mismatches are errors. Fingerprint
includes mode, deployment identity, services and every selected version/generation;
selection order does not change identity. Latest is an indexing view, not evidence
that all selected commits were deployed together.

`save_context` persists an immutable manifest and retention pins; `load_context`
checks its fingerprint and re-authorizes every repository. Saving is idempotent.
`release_context` explicitly releases those pins. `register_deployment` records an
immutable mapping (changed versions require a new deployment key);
`release_deployment` releases it. These write APIs belong to CLI/maintenance code,
never a read-only MCP request. Query-time selection is read-only and can be used
without persisting a context. Such ephemeral selections do not pin versions beyond
their read transaction; save the manifest when retention across calls is required.

GC excludes snapshots referenced by saved contexts or deployment maps even with
`keep_retired=0`. Shared transaction advisory locking serializes pin registration /
release and GC; foreign keys additionally prevent unsafe deletion. Context tables
are retention owners, not snapshot-owned facts, and are not in the snapshot GC
allowlist. After all pins are released normal retention rules apply.
