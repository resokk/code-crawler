# Capability: bpmn-schema-adapter

## ADDED Requirements

### Requirement: Discover BPMN XML and safely parse namespaces without DTD, XXE or network access.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: BPMN with gateway and two flows
- GIVEN BPMN with gateway and two flows
- WHEN indexing
- THEN both transitions and guards remain addressable

### Requirement: Extract process, start/end events, service/user tasks, subprocesses, gateways, sequence flows and conditions.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: BPMN task with external worker type
- GIVEN BPMN task with external worker type
- WHEN indexing repo A alone
- THEN deferred reference is stored without reading repo B

### Requirement: Preserve process variables, expressions, input/output mappings, extension elements and engine hints.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: BPMN document with external XML entity
- GIVEN BPMN document with external XML entity
- WHEN parsing
- THEN no network/file expansion occurs

### Requirement: Represent graph edges as typed UCM relations with SourceRange/Evidence, not opaque JSON.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Malformed BPMN XML
- GIVEN Malformed BPMN XML
- WHEN indexing
- THEN diagnostics and partial coverage are saved, no false flow links

### Requirement: Cross-repository independence
The adapter MUST index one repository without relying on the state of other repositories.

#### Scenario: Target only exists elsewhere
- GIVEN a source reference points to a target from another repository
- WHEN the source repository is indexed
- THEN its UCM publish succeeds with a deferred external selector and no cross-snapshot relation
