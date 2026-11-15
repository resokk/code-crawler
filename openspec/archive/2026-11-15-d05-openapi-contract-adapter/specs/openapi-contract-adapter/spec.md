# Capability: openapi-contract-adapter

## ADDED Requirements

### Requirement: Discover YAML/JSON by root openapi field; support dialect-aware OpenAPI 3.0, 3.1 and 3.2.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: OpenAPI 3.0/3.1/3.2 examples
- GIVEN OpenAPI 3.0/3.1/3.2 examples
- WHEN parsing
- THEN version-specific meanings are retained

### Requirement: Extract operations, params, body, responses, schemas, fields, media types, security, callbacks and webhooks.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Node schema self-reference
- GIVEN Node schema self-reference
- WHEN parsing
- THEN finite reference graph is generated

### Requirement: Support composition, discriminator, required/nullable and recursive local references without unbounded expansion.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Remote HTTPS ref
- GIVEN Remote HTTPS ref
- WHEN indexing
- THEN deferred schema reference is stored without network call

### Requirement: Support OpenAPI 3.2 QUERY, additionalOperations and querystring; preserve unsupported vendor extensions with diagnostics.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: OpenAPI 3.2 QUERY and querystring
- GIVEN OpenAPI 3.2 QUERY and querystring
- WHEN indexing
- THEN typed operation and parameter survive

### Requirement: Resolve local and repository-relative refs; keep remote URI references deferred with no network access.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: OpenAPI GET endpoint
- GIVEN OpenAPI GET endpoint
- WHEN reading UCM
- THEN path, method and source evidence are available

### Requirement: Cross-repository independence
The adapter MUST index one repository without relying on the state of other repositories.

#### Scenario: Target only exists elsewhere
- GIVEN a source reference points to a target from another repository
- WHEN the source repository is indexed
- THEN its UCM publish succeeds with a deferred external selector and no cross-snapshot relation
