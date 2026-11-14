# Capability: vbscript-ucm-adapter

## ADDED Requirements

### Requirement: Integrate ANTLR VBScript grammar and parser diagnostics with SourceAdapter registry.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Two differently cased VBScript references
- GIVEN Two differently cased VBScript references
- WHEN resolution
- THEN case-insensitive lookup targets same symbol where unambiguous

### Requirement: Extract sub/function declarations, parameters, class/method/property statements, scopes and explicit calls.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Function builds DELETE string without Execute
- GIVEN Function builds DELETE string without Execute
- WHEN indexing
- THEN there is SQL candidate but no proven execution site

### Requirement: Detect static ADODB and SQL literal/build patterns without equating strings with execution.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: ADODB.Connection.Execute with SQL text
- GIVEN ADODB.Connection.Execute with SQL text
- WHEN analysis
- THEN execution sink and statement relation carry Evidence

### Requirement: Distinguish late-bound COM object methods and dynamic Eval/CreateObject calls as partial external references.
The adapter MUST preserve language-specific semantics, stable UCM identity and explicit uncertainty.

#### Scenario: Late-bound COM dispatch
- GIVEN Late-bound COM dispatch
- WHEN analysis
- THEN external selector remains partial with documented coverage

### Requirement: Local indexing and transparent coverage
Every adapter MUST be independent of external repository availability and MUST emit evidence for inferred local links and deferred selectors for remote targets.

#### Scenario: Remote target missing
- GIVEN source code references a symbol, endpoint or resource in an unavailable other repository
- WHEN the current repository is indexed
- THEN publishing can complete without a guessed cross-repository relation, and ExternalReference remains discoverable
