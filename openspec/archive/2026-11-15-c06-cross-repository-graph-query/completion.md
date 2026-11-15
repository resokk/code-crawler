# Completion: C06 cross-repository graph query

Added a bounded forward traversal API and read-only MCP tool. Local canonical
Relations stay within selected snapshots; ExternalReference nodes invoke C04/C05
for query-time declaration identities. Ambiguous, partial and unresolved candidates
are reported without continuation. No persistent graph or schema change is needed.

The version-1 response retains scoped snapshots/generations, parent-step path order,
Evidence, certainty, resolution, coverage, effective limits and truncation reasons.
Depth, fanout, node, repository-hop, result and time bounds are enforced. Context
repositories are authorized before lookup and each remote transition is authorized;
all selected snapshots are verified and leased in a read-only repeatable-read view.
Timeout rolls back its transaction/savepoint and returns a coherent partial prefix;
caller cancellation propagates. MCP validates JSON through the strict canonical
context contract and obtains grants exclusively from server configuration.

Contract and fixture expectations: [cross-repository-graph.md](../../../docs/cross-repository-graph.md).
Acceptance tests cover two repositories, local and A→B→A cycles, depth 3, ambiguous
fanout, partial/unsupported references, response bounds, denied/private targets,
foreign snapshots, publication changes, rollback, timeout and cancellation recovery.

Validation: ruff check and format passed. Full mandatory PostgreSQL 15 suite:
1245 passed. An initial full run exposed a strict-model MCP JSON conversion issue;
the transport conversion was corrected and the complete suite rerun successfully.
