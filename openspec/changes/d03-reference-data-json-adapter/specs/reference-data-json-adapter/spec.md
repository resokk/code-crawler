# Capability: reference-data-json-adapter

## ADDED Requirements

### Requirement: Detect configurable type-data.json file patterns and validate JSON structure/version.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: currencies-data.json with records
- GIVEN currencies-data.json with records
- WHEN indexing
- THEN dataset is created without declaring table currencies

### Requirement: Extract ReferenceDataset, Field, Record, keys, value types and exact JSON pointers.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Valid record with code field
- GIVEN Valid record with code field
- WHEN reading source evidence
- THEN the correct JSON pointer and bytes are available

### Requirement: Distinguish source presence from runtime load/deployment status.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Malformed record
- GIVEN Malformed record
- WHEN indexing
- THEN partial coverage and diagnostic are recorded

### Requirement: Apply bounded record handling and partial diagnostics for malformed entries.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Data file merely committed
- GIVEN Data file merely committed
- WHEN querying load status
- THEN deployment is not claimed

### Requirement: Cross-repository independence
The adapter MUST index one repository without relying on the state of other repositories.

#### Scenario: Target only exists elsewhere
- GIVEN a source reference points to a target from another repository
- WHEN the source repository is indexed
- THEN its UCM publish succeeds with a deferred external selector and no cross-snapshot relation
