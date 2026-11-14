# Capability: graphql-java-bindings

## ADDED Requirements

### Requirement: Support Spring GraphQL QueryMapping, MutationMapping, SubscriptionMapping, SchemaMapping and BatchMapping.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Mutation createLoan matches one Java MutationMapping
- GIVEN Mutation createLoan matches one Java MutationMapping
- WHEN analysis
- THEN root operation links to method with evidence

### Requirement: Resolve typed field identity including owner type, field name, argument types and return types.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Loan.repaymentSchedule field has SchemaMapping
- GIVEN Loan.repaymentSchedule field has SchemaMapping
- WHEN analysis
- THEN nested field links to resolver and onward to SQL through CALLS

### Requirement: Detect supported GraphQL Java DataFetcher registration and DGS profiles, with version-specific capabilities.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Two compatible resolvers for one field
- GIVEN Two compatible resolvers for one field
- WHEN resolution
- THEN AMBIGUOUS with candidates is returned

### Requirement: Treat default property/data fetching as possible but not a fictitious handler; ambiguous resolvers remain uncertain.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: No explicit resolver uses default getter semantics
- GIVEN No explicit resolver uses default getter semantics
- WHEN analysis
- THEN no fake Java resolver relation is emitted

### Requirement: Link field→local Java symbol→existing CALLS→SQL without reparsing SQL; preserve deferred external target references.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: External federated subgraph
- GIVEN External federated subgraph
- WHEN indexing
- THEN deferred selector rather than global read

### Requirement: Local indexing and transparent coverage
Every adapter MUST be independent of external repository availability and MUST emit evidence for inferred local links and deferred selectors for remote targets.

#### Scenario: Remote target missing
- GIVEN source code references a symbol, endpoint or resource in an unavailable other repository
- WHEN the current repository is indexed
- THEN publishing can complete without a guessed cross-repository relation, and ExternalReference remains discoverable
