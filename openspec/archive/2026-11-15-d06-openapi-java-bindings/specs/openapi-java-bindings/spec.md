# Capability: openapi-java-bindings

## ADDED Requirements

### Requirement: Parse effective Spring MVC/WebFlux mappings from class/method annotations including HTTP method, routes, consumes and produces.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Matching OpenAPI GET and Spring GetMapping with class prefix
- GIVEN Matching OpenAPI GET and Spring GetMapping with class prefix
- WHEN binding
- THEN operation points to one handler with two-source evidence

### Requirement: Derive route candidate keys without losing original path parameter names; include known base/server context.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: GET contract but POST controller
- GIVEN GET contract but POST controller
- WHEN binding
- THEN no false RESOLVED relation is created

### Requirement: Resolve API operation to Java handler only when route, HTTP method and framework constraints match uniquely.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Two compatible controllers
- GIVEN Two compatible controllers
- WHEN binding
- THEN status AMBIGUOUS and alternatives are returned

### Requirement: Represent ambiguous controllers as candidates and unresolved or client calls as ExternalReference.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: FeignClient for remote loan-service
- GIVEN FeignClient for remote loan-service
- WHEN indexing
- THEN selector includes service, method and path with deferred target

### Requirement: Map DTO argument/response types only from signatures and explicit annotations; connect to existing Java Call Graph and SQL.
The adapter MUST implement this behavior while preserving UCM Evidence, Coverage and Resolution.

#### Scenario: Handler calls service and SQL
- GIVEN Handler calls service and SQL
- WHEN traversal
- THEN API to handler to SQL path is accessible

### Requirement: Cross-repository independence
The adapter MUST index one repository without relying on the state of other repositories.

#### Scenario: Target only exists elsewhere
- GIVEN a source reference points to a target from another repository
- WHEN the source repository is indexed
- THEN its UCM publish succeeds with a deferred external selector and no cross-snapshot relation
