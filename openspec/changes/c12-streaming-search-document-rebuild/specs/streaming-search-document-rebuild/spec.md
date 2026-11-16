# Capability: streaming-search-document-rebuild

## ADDED Requirements

### Requirement: Bounded projection memory
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Bounded projection memory
- GIVEN A published snapshot contains more than one million UCM facts
- WHEN rebuilding search documents
- THEN the projector streams bounded batches and does not materialize all canonical entities/documents in Python memory

### Requirement: Stable equivalence
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Stable equivalence
- GIVEN One fixture is indexed with old and new projection algorithms
- WHEN results are compared under the same redaction and version
- THEN document IDs, contents, hashes, provenance and counts are equal

### Requirement: Atomic generation
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Atomic generation
- GIVEN Projection fails after 40 percent of documents are staged
- WHEN a reader opens the current generation
- THEN the previous complete generation is still visible, and incomplete generation is not published

### Requirement: Authorization
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Authorization
- GIVEN Caller lacks repository grant
- WHEN rebuild is invoked
- THEN it is rejected before reading source facts or calling redaction

### Requirement: Concurrent publication
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Concurrent publication
- GIVEN A newer canonical snapshot is published during projection
- WHEN the projector attempts generation swap
- THEN it cannot expose documents from one snapshot under a different publication pointer

### Requirement: Policy change
The system MUST implement this scenario using evidence-backed typed facts and an explicit version context.

#### Scenario: Policy change
- GIVEN Redaction policy version changes
- WHEN projection rebuilds
- THEN a new generation is created without changing canonical raw source Evidence

### Requirement: No false confirmed relationship
A declaration key or semantic similarity alone MUST NOT be treated as proof that an external runtime call executed.

#### Scenario: Partial source coverage
- GIVEN source/framework identity or runtime environment is incomplete
- WHEN discovery or projection executes
- THEN coverage is PARTIAL or UNSUPPORTED, and no new STATIC_PROVEN runtime edge is manufactured
