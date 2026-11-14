# Capability: kotlin-ucm-adapter

## ADDED Requirements

### Requirement: Discover Kotlin .kt/.kts with explicit support and diagnostics for Kotlin scripts.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Two overloaded Kotlin functions
- GIVEN Two overloaded Kotlin functions
- WHEN indexing
- THEN they keep separate signature IDs

### Requirement: Extract packages, imports, classes, interfaces, objects, functions, constructors, properties, scopes and occurrences.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Extension function invocation
- GIVEN Extension function invocation
- WHEN resolution
- THEN receiver and evidence are preserved without guessing missing types

### Requirement: Handle overloads, extension functions, receivers, nullable types and generic signatures without false resolution.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Kotlin calls Java method in same repository
- GIVEN Kotlin calls Java method in same repository
- WHEN resolution
- THEN local CALLS relation is inferred only with sufficient evidence

### Requirement: Resolve local Kotlin calls and supported Java interoperability via shared UCM symbols, preserving unknown targets.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Kotlin script uses unknown dynamic call
- GIVEN Kotlin script uses unknown dynamic call
- WHEN analysis
- THEN coverage PARTIAL and no fabricated definite target

### Requirement: Local indexing and transparent coverage
Every adapter MUST be independent of external repository availability and MUST emit evidence for inferred local links and deferred selectors for remote targets.

#### Scenario: Remote target missing
- GIVEN source code references a symbol, endpoint or resource in an unavailable other repository
- WHEN the current repository is indexed
- THEN publishing can complete without a guessed cross-repository relation, and ExternalReference remains discoverable
