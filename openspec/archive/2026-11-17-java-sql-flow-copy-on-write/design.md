# Design

_SqlFlow.clone shares variables and marks both sides shared. Branch-local frames
copy their mapping structure; choices, reads and query-list containers stay local.
_writable detaches the complete variables/saved-binding graph only on the first
write. Separate identity memos preserve aliases between variables and between
values held by distinct variables, including shadowed bindings. Immutable spans,
fragments and reasons remain shared, extending main's selective clone optimization.

The base legacy _Flow has a no-op write hook. SQL flows override it. Barriers cover
declaration/saved-scope capture, assignment, dirty consumption, builder mutation
and append evaluated recursively inside expressions. Mutation handlers reacquire
variable references after detachment. Scope exit changes only the binding map;
it shallow-copies that map when shared and retains the value-write guard.

Internal mutation of variables/_Value must always pass _writable first. This is a
private protocol, not an externally mutable mapping API. Direct clone tests call
the barrier before manual mutation. Legacy recovery remains eager and unchanged.
Constants are treated as read-only; unknown builder alias/escape behavior remains
partial. Query objects are shared as before; their path-level reason propagation
is unchanged. Path ordering, truncation and limits are unchanged. Equivalent-state
merging is explicitly deferred.

Compare full UcmBatch JSON against the old eager-deepcopy oracle over assignments,
constants/parameters without literals, shadowing, builder aliases/mutations, dirty
reads, ternaries, loops and path truncation. Measure a fixed synthetic read-heavy
and write-heavy corpus in fresh processes against current main's clone and against
historical deepcopy. Report fact digest, time, RSS, clone/materialization counts,
fixture/source hashes and environment; do not generalize to production throughput.
