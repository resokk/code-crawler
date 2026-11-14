# Capability: graphql-schema-adapter

## ADDED Requirements

### Requirement: Discover .graphql/.graphqls/.gql SDL and supported introspection JSON sources.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Schema uses custom root type RootQuery
- GIVEN Schema uses custom root type RootQuery
- WHEN parsing
- THEN root operation fields reflect RootQuery rather than assuming Query

### Requirement: Parse local schema definitions and type/schema extensions into consistent composed schema, with source provenance.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: SDL with type and extend type in two files
- GIVEN SDL with type and extend type in two files
- WHEN composition
- THEN one type exposes all fields with per-source evidence

### Requirement: Model SCALAR, OBJECT, INPUT_OBJECT, ENUM, INTERFACE, UNION, field arguments and exact list/non-null modifiers.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Field returns list of non-null Loan within non-null list
- GIVEN Field returns list of non-null Loan within non-null list
- WHEN normalizing
- THEN all nested modifiers are retained

### Requirement: Extract actual Query/Mutation/Subscription root type fields, custom root names, directives and deprecations.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Introspection JSON lacks SDL coordinates
- GIVEN Introspection JSON lacks SDL coordinates
- WHEN normalizing
- THEN source position is explicitly unavailable rather than fabricated

### Requirement: Preserve unknown federation extensions and unresolved schema components without runtime GraphQL execution.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Undefined referenced type
- GIVEN Undefined referenced type
- WHEN validation
- THEN diagnostics and partial coverage are returned

### Requirement: Local indexing and transparent coverage
Every adapter MUST be independent of external repository availability and MUST emit evidence for inferred local links and deferred selectors for remote targets.

#### Scenario: Remote target missing
- GIVEN source code references a symbol, endpoint or resource in an unavailable other repository
- WHEN the current repository is indexed
- THEN publishing can complete without a guessed cross-repository relation, and ExternalReference remains discoverable
