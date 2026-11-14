# Capability: reference-data-loader-analysis

## ADDED Requirements

### Requirement: Find supported Java/Groovy/PLPlus loader patterns and their dataset identity.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Loader maps field code into target column
- GIVEN Loader maps field code into target column
- WHEN analyzing
- THEN ReferenceField to DB column path with mapping evidence exists

### Requirement: Extract DataLoadOperation and DataLoadMapping with field paths, transformations and DB-context provenance.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Dynamic reflective field transformation
- GIVEN Dynamic reflective field transformation
- WHEN analyzing
- THEN target remains PARTIAL without false resolved column

### Requirement: Link to existing SQL_EXECUTE, ORM and DATA_ACCESS facts instead of building a duplicate SQL graph.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Loader contains SQL INSERT
- GIVEN Loader contains SQL INSERT
- WHEN indexing
- THEN statement is discovered but never executed by crawler

### Requirement: For reflection/dynamic mapping return PARTIAL/UNKNOWN and evidence, not guessed targets.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Dataset in A and loader in B
- GIVEN Dataset in A and loader in B
- WHEN indexing A
- THEN no cross-repository scan occurs

### Requirement: Cross-repository independence
The adapter MUST index one repository without relying on the state of other repositories.

#### Scenario: Target only exists elsewhere
- GIVEN a source reference points to a target from another repository
- WHEN the source repository is indexed
- THEN its UCM publish succeeds with a deferred external selector and no cross-snapshot relation
