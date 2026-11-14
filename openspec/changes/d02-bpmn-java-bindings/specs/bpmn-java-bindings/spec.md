# Capability: bpmn-java-bindings

## ADDED Requirements

### Requirement: Implement version-aware Camunda and Flowable binding profiles.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: ServiceTask bound to one Spring bean
- GIVEN ServiceTask bound to one Spring bean
- WHEN analyzing
- THEN task to handler relation includes BPMN and Java evidence

### Requirement: Resolve JavaDelegate, delegateExpression, Spring bean, external worker/topic to local Java symbols.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Two compatible delegate beans
- GIVEN Two compatible delegate beans
- WHEN binding
- THEN AMBIGUOUS with both candidates is returned

### Requirement: Track process variable mapping as typed facts with uncertain data lineage made explicit.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: External worker in another repository
- GIVEN External worker in another repository
- WHEN indexing
- THEN deferred selector is emitted

### Requirement: Create evidence-backed BPMN task to Java handler relations; ambiguous beans remain ambiguous.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Delegate invoking SQL
- GIVEN Delegate invoking SQL
- WHEN local graph traversal
- THEN BPMN to Java to SQL path composes from existing relations

### Requirement: Cross-repository independence
The adapter MUST index one repository without relying on the state of other repositories.

#### Scenario: Target only exists elsewhere
- GIVEN a source reference points to a target from another repository
- WHEN the source repository is indexed
- THEN its UCM publish succeeds with a deferred external selector and no cross-snapshot relation
