# Capability: bpmn-worker-discovery

## ADDED Requirements

### Requirement: Typed definition projection
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Typed definition projection
- GIVEN A D02 supported explicit external worker handler is declared in repo B
- WHEN its snapshot is published
- THEN a BPMN_WORKER catalog entry exists with handler identity and dual-source Evidence where available

### Requirement: Reference is not declaration
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Reference is not declaration
- GIVEN Repo A BPMN task references worker type accounting but no handler is defined
- WHEN repo A is indexed
- THEN it adds an ExternalReference but not a false BPMN_WORKER definition entry

### Requirement: Ambiguity
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Ambiguity
- GIVEN Two handler declarations are compatible with a worker type
- WHEN C04 resolves from another repo
- THEN both candidates are retained and resolution remains AMBIGUOUS/PARTIAL, not unique by arbitrary ordering

### Requirement: No runtime proof
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: No runtime proof
- GIVEN Only a matching worker annotation is statically visible
- WHEN global graph traversal returns an identity hop
- THEN the hop is labelled declaration identity with partial runtime coverage, not a proven job execution

### Requirement: Isolation and versioning
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Isolation and versioning
- GIVEN Deployment context pins old repo B snapshot while latest contains another worker
- WHEN query uses pinned context
- THEN selected snapshot drives discovery and authorization

### Requirement: No false confirmed relationship
A declaration key or semantic similarity alone MUST NOT be treated as proof that an external runtime call executed.

#### Scenario: Partial source coverage
- GIVEN source/framework identity or runtime environment is incomplete
- WHEN discovery or projection executes
- THEN coverage is PARTIAL or UNSUPPORTED, and no new STATIC_PROVEN runtime edge is manufactured
