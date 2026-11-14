# Capability: openspec-archive-policy

## ADDED Requirements

### Requirement: Define active openspec/changes versus completed openspec/changes/archive and a stable naming convention.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Change fully implemented and tests passed
- GIVEN Change fully implemented and tests passed
- WHEN archiving
- THEN its proposal/design/specs/tasks remain accessible under archive

### Requirement: After implementation + CI + acceptance, archive proposal/design/specs/tasks with completion receipt and commit/CI link.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Open checkboxes remain
- GIVEN Open checkboxes remain
- WHEN attempting archive
- THEN change stays active until tests/criteria are verified

### Requirement: Maintain roadmap with dependencies, current baseline SHA, priority and explicit open criteria.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: LLM starts feature
- GIVEN LLM starts feature
- WHEN reading roadmap
- THEN dependencies and single-change scope are explicit

### Requirement: Provide agent execution instructions: implement one change at a time, do not invent new capabilities, preserve tests/docs, stop at scope boundary.
The system MUST satisfy this requirement with auditable results and clear failure behavior.

#### Scenario: Existing historical changes removed earlier
- GIVEN Existing historical changes removed earlier
- WHEN recovering history
- THEN Git source is preserved without silently claiming completion

### Requirement: Auditable and reproducible actions
All destructive or publication-related operations MUST be observable, safe under failure, and prevent modification of unrelated repositories.

#### Scenario: Unrelated repository is active
- GIVEN another repository has a published or pinned snapshot
- WHEN this feature operates on one selected repository
- THEN the other repository remains readable and unaffected
