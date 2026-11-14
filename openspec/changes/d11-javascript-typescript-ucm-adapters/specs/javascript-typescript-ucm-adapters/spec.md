# Capability: javascript-typescript-ucm-adapters

## ADDED Requirements

### Requirement: Use separate versioned adapters for .js/.jsx and .ts/.tsx, with file-routing and TS project config.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: TS module imports another local module
- GIVEN TS module imports another local module
- WHEN indexing
- THEN reference target matches the correct file with Evidence

### Requirement: Extract exports/imports, functions, classes, arrow functions, methods, variables, scopes, occurrences and type references.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: JS dynamic import with variable path
- GIVEN JS dynamic import with variable path
- WHEN resolution
- THEN target remains UNRESOLVED rather than arbitrary match

### Requirement: Resolve local module paths, reexports and deterministic same-repository calls; dynamic imports/calls preserve uncertainty.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Two TS overload signatures
- GIVEN Two TS overload signatures
- WHEN indexing
- THEN symbols and callable occurrences remain distinguishable

### Requirement: Capture supported fetch/axios HTTP client method/URL expressions as typed external API references.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: fetch call to remote REST endpoint
- GIVEN fetch call to remote REST endpoint
- WHEN indexing
- THEN ExternalReference stores known method/path and dynamic portions as partial

### Requirement: Preserve TS overloads, generics and interface declarations without claiming runtime implementation.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: TS type-only import
- GIVEN TS type-only import
- WHEN analysis
- THEN type reference does not become definite runtime CALLS

### Requirement: Local indexing and transparent coverage
Every adapter MUST be independent of external repository availability and MUST emit evidence for inferred local links and deferred selectors for remote targets.

#### Scenario: Remote target missing
- GIVEN source code references a symbol, endpoint or resource in an unavailable other repository
- WHEN the current repository is indexed
- THEN publishing can complete without a guessed cross-repository relation, and ExternalReference remains discoverable
