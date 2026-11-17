# External reference candidate search (C04)

`search.resolve_external_reference(conn, source_repository_key, reference_id,
context, *, allowed_repositories, limit=50)` reads one ExternalReference from its
exact C03-selected source snapshot and searches C02 declarations only in the same
immutable context. It returns a typed `CandidateResolution` (`contract_version=1`),
source/origin IDs, context fingerprint, source Evidence paths, candidates, resolution,
coverage and reasons. It never persists cross-repository Relations or changes the
canonical ExternalReference (which remains UNRESOLVED).

Both source and every selected target repository require explicit trusted grants.
Absent/insufficient authorization fails before reading facts. Public MCP exposure
and principal ACL integration belong to A02/C09; this backend API never accepts an
untrusted client-provided allowlist as an authorization decision.

The entire query runs in read-only REPEATABLE READ (or an existing compatible
transaction). Fanout is at most 32 selected repositories and 1..200 candidates;
SQL fetches limit+1, ordered by repository/snapshot/entity. Truncation or an unavailable
catalog generation yields PARTIAL, even if only one visible candidate remains.
Pinned retired versions are supported. No fallback to another snapshot, global latest,
name similarity or a remote network lookup occurs.

Selector keys preserve case and namespace: Symbol FQN + exact ordered signature
(unknown differs from zero parameters), DB database/version/catalog/schema/kind/name,
HTTP service/method/path, BPMN process/worker IDs, Kafka topic IDs. Known framework
prefixes remain framework selectors; they cannot be promoted to ordinary symbol
proof. Connection aliases require an unambiguous canonical DatabaseContext in the origin
entity’s source file; an alias
is never treated as a global database identity. Missing schema uses explicit context
search-path selection, without guessing across schemas. Dynamic identifiers remain
partial. Resolver version 3 supports C10/C11 declaration candidates:
Kafka selectors use the existing D07 JSON `[cluster, environment, topic]` identity
(with an optional repository-local site suffix). Only exact topic and explicitly
known cluster/environment constrain lookup; the site suffix is never global
identity. Malformed/dynamic identities have no lookup key. BPMN worker type is
matched with the exact engine recorded by D02 source Evidence; absent/conflicting
engine provenance produces no match. Dynamic worker expressions are not evaluated.
Worker candidates expose optional `handler_id` to the canonical Java Method;
BPMN_WORKER_HANDLER retains annotation + method/contract Evidence. These candidates
always remain PARTIAL (or AMBIGUOUS), including with one matching declaration;
there is no proof of runtime activation or delivery. OpenAPI operations (D05) are
HTTP candidates: explicit service constraints require a matching deployment mapping.
Without that mapping no arbitrary repository is selected. Contract facts do not
declare canonical service identity/implementation binding, so HTTP matches stay
PARTIAL even when unique. Paths are literal: server base-path expansion and route
template execution semantics are not inferred.

RESOLVED means one exact **declaration selector identity** in the selected indexed
context, never proof of invocation/deployment. It requires a complete selector,
STATIC_PROVEN/COMPLETE source facts, compatible version constraints and accessible
source/target Evidence paths. Symbol names without signature proof remain PARTIAL. Resolver analyzer version 3
also treats adapter placeholders (`kotlin.unknown`, `groovy.dynamic`,
`vbscript.Variant`, TypeScript `any`/`unknown`) as incomplete type identity,
including nested generic/array types. Exact-key candidates remain discoverable,
but matching placeholder spellings cannot produce RESOLVED/STATIC_PROVEN.
Fully qualified concrete names such as `org.unknown` are not placeholder matches.
Multiple compatible candidates produce AMBIGUOUS; no candidates produces UNRESOLVED.
Hints can constrain lookup (repository key, exact commit/snapshot ID), but never
serve as proof themselves. Unknown framework semantics and partial source facts
never become STATIC_PROVEN. Candidate discovery certainty and source fact certainty
are returned separately.

HTTP candidates additionally retain the originating OpenAPI `contract_id`; contracts
with the same route remain separate candidates.

Evidence paths include repository/snapshot/entity/generation, archived source file
hash/path/range and the matching rule. Source bytes can be obtained explicitly with
`source_evidence.read_source_fragment`; search does not copy entire files into every
candidate. Legacy/unavailable source is explicit and prevents conclusive resolution.
The disposable [C05 resolver cache](resolver-cache.md) can reuse a verified result;
authorization and generation checks remain mandatory. Misses still compute C04
without writes from a read-only request. C04 itself introduces no storage schema.

Example (trusted backend; grants come from authorization, not request parameters):

```python
context = await select_context(
    conn, "LATEST_INDEXED", ("app", "library"), allowed_repositories=grants
)
result = await search.resolve_external_reference(
    conn, "app", external_id, context, allowed_repositories=grants, limit=20
)
```

For reusable selections call `save_context`; future queries load the same manifest
with `load_context`. An ephemeral context still selects exact versions for this
call, but persistent retention requires saving it. `selected_reader` provides the
same authorized, retained-snapshot read path inside an existing read-only transaction.
