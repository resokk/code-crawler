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

### Requirement: Bounded syntax and failed-attempt isolation
The adapter MUST report UTF-8, grammar, declaration and complexity errors with
structured diagnostics and MUST preserve the previous published snapshot.

#### Scenario: Malformed or excessive source
- GIVEN a syntax error, duplicate case-insensitive declaration, invalid UTF-8 or a resource-limit violation
- WHEN analysis runs
- THEN no recovered semantic batch is published and diagnostics identify the source path/range where available.

### Requirement: Provenance-bound execution recognition
The adapter MUST require tracked ADODB receiver provenance and MUST invalidate
unsafe local definitions before attaching recovered SQL statements to execution sites.

#### Scenario: Rebound, shadowed or unknown receiver
- GIVEN an arbitrary Execute method, a shadowed CreateObject, a reassigned receiver or an unknown ByRef call
- WHEN SQL-looking text is analyzed
- THEN it may produce candidates but does not create a guessed ADODB execution site.

#### Scenario: Partial query or command options
- GIVEN dynamic SQL fragments or non-text ADODB command options
- WHEN an ADODB call is analyzed
- THEN no complete SQL execution semantics are asserted for that text; partial facts retain reasons and Evidence.

### Requirement: Adapter-scoped incremental equivalence
The adapter MUST preserve deterministic facts and participate in existing registry fingerprints.

#### Scenario: Unchanged bytes and new adapter version
- GIVEN a mixed-language published snapshot
- WHEN indexing repeats without edits or the VBScript adapter version changes
- THEN unchanged facts are reused, or only the VBScript scope is reanalyzed with equivalent canonical facts and an updated SourceAnalysis report.
