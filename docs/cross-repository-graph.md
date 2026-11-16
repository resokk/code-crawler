# Cross-repository graph traversal (C06)

`search.trace_cross_repository(conn, repository_key, entity_id, context, *,
allowed_repositories, depth=4, fanout=20, max_nodes=100, max_repository_hops=2,
max_results=100, timeout_ms=5000, relation_kinds=())` performs deterministic forward
breadth-first traversal in the exact immutable C03 context. It reads canonical
local Relations and calls C04/C05 only at ExternalReference nodes. No global graph,
canonical edge, cache entry or publication is written by a request.

All context repositories require trusted grants before any read. The start repository
must be selected. Snapshot ownership, retained state and catalog generations are
verified; shared transaction leases cover all selected snapshots. A missing catalog
generation is explicit partial availability, never a reason to switch versions.

## Edges and path semantics

The version-1 typed response contains scoped nodes, ordered steps, context fingerprint,
limits, expanded node count, Coverage, truncation and reasons. Every step records
its source/target repository and snapshot, depth, repository-hop count, parent-step
index and Evidence paths. Follow `parent_step` to reconstruct an ordered branch.
Local steps retain canonical relation ID/kind, resolution, certainty and coverage.
Remote steps retain C04 candidates and its source/target evidence; their assertion
scope is DECLARATION_IDENTITY, not an assertion that a runtime call executes.

Only unique RESOLVED targets continue. AMBIGUOUS, PARTIAL and UNRESOLVED targets are
reported without following any candidate. No ambiguity-promotion policy is provided.
Local relation filters apply only to canonical edges; excluding EXTERNAL_DEPENDENCY
can prevent reaching a deferred reference. Reverse global lookup is not inferred.

Cycles are reported and stopped. Dominated visits (same scoped node with no better
depth/hop budget) do not expand again. Alternative paths with more remaining hop
budget can still expand; the result cap bounds repeated path occurrences.

## Bounds and cancellation

Depth is 1..12; fanout 1..50; nodes/results 1..500; repository hops 0..8; timeout
1..30000 ms. Nodes include returned candidate alternatives, not just expanded nodes.
The total result budget counts emitted steps plus candidate records. Local Evidence
and coverage reasons are limited to 8 each; all omissions are marked explicitly.
Remote resolver fanout is further restricted by remaining response budget.

Reaching a depth/hop/result/node/time bound yields `truncated=true` and PARTIAL
coverage with a stable reason; it never looks like a complete traversal. At the
repository-hop bound, deferred references are reported without another resolver call.
A resolved target omitted by a response bound has `target=None`, `truncated=true`
and a stop reason: this is a bounded projection, not a change to canonical resolution.

One read-only REPEATABLE READ transaction covers the request. A compatible existing
transaction uses a savepoint. Timeout returns the collected coherent prefix after
rolling back the read/savepoint; caller cancellation propagates and releases request
resources. No filesystem fallback or source execution occurs. Evidence paths refer
to the selected archived sources; raw bytes are obtained through authorized readers.

The MCP tool validates its JSON context with the canonical strict JSON contract
(including JSON arrays for selections/services). It uses the server's
DISCOVERY_REPOSITORY_KEYS scope. A client can select
an immutable context within that scope, but cannot grant itself access. This does
not replace future principal-specific ACL work (A02). Existing single-repository
`trace_dependency` remains unchanged.

## Acceptance fixture

The PostgreSQL fixture archives sources for `repo` and `target`, publishes both,
and selects a single immutable context. A method in `repo` has a canonical
EXTERNAL_DEPENDENCY to an exact external signature. The expected ordered path is
local relation → external declaration identity in `target` → local relation.
Each step has a parent index and archived Evidence. A return selector from `target`
to the original method closes A→B→A without repeated expansion; depth 3 returns
only the first three edges with DEPTH_LIMIT.

Four matching remote declarations produce one AMBIGUOUS step with four candidates
and no continuation. Missing, partially inferred and unsupported references preserve
uncertainty. A scope without `target` returns no target node/candidate; selecting an
unauthorized context fails before database access. Publication changes and rollback
are tested separately from explicitly selected snapshots. Timeout and cancellation
are exercised with a real PostgreSQL query inside a savepoint, followed by another
successful query on the same connection. No schema migration is needed.

A02 authentication additionally requires read/discover permissions and membership
for the root and every repository in the supplied context, intersected with the
server discovery scope before DB access. Context repository/snapshot IDs are
verified by the existing reader; they are references, not authorization grants.
See [mcp-access-control.md](mcp-access-control.md).
