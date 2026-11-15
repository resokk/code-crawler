# Design: VBScript symbols, calls and embedded SQL

## Baseline
VBScript is in target language coverage but no canonical extractor exists.

## Architecture
### Decision 1
Integrate ANTLR VBScript grammar and parser diagnostics with SourceAdapter registry.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 2
Extract sub/function declarations, parameters, class/method/property statements, scopes and explicit calls.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 3
Detect static ADODB and SQL literal/build patterns without equating strings with execution.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 4
Distinguish late-bound COM object methods and dynamic Eval/CreateObject calls as partial external references.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

### Decision 5
Preserve case-insensitive identifier semantics and byte-accurate source positions.

Use deterministic logical keys, explicit source path/line/byte coordinates, typed UCM relations and local symbol resolution. Unknown dynamic behavior must keep PARTIAL or UNRESOLVED with reasons, not a guessed RESOLVED edge.

## SourceAdapter lifecycle
Detect file → safe parse → AST/language-specific facts → local reference resolution → UCM Batch → centralized PostgreSQL staging/validation/publication. Record file ownership and negative/positive dependencies for incremental reanalysis.

## Security and failure policy
No network lookups by default, no execution, no trust in input code or metadata. Constrain parser complexity and return diagnostics on malformed input. Failed analysis must not replace a currently published snapshot.

## Compatibility and tests
Add new UCM EntityType/RelationKind only if necessary, using forward migrations. Preserve existing Java/SQL/BPMN facts and compare full vs incremental output on same fixture.

## Implemented profile v1

The adapter uses the dedicated ANTLR 4.13.2 grammar in `grammars/vbscript/` and
existing UCM Symbol/Scope/Occurrence/Operation/Value/SQL/Relation models; no schema
migration is needed. All plaintext `.vbs` case variants are explicit registry
routes. Parser failures, duplicate canonical declarations and resource limits raise
structured AdapterError diagnostics; no recovered syntax facts replace publication.

Names/keys use casefold, while occurrences and archived bytes retain source spelling.
A synthetic script class and `<run>` callable own top-level work. Property accessors
are separate `.get/.let/.set` methods. Local class instances and same-file callable
arity support lexical INFERRED links. Files do not implicitly share a host/global
namespace: external calls and missing classes stay deferred selectors. Dynamic code
is a dispatch barrier, never a target guess.

Only local, straight-line object/string definitions are propagated. Static strings,
`&`, and `+` of known strings produce constructions; unknown pieces are partial.
SQLGlot is reused one candidate at a time, with VBScript-origin Evidence. ADODB
Connection.Execute / Recordset.Open require literal CreateObject receiver provenance;
Command.Execute also requires captured CommandText and CommandType=1. Rebinding,
unknown calls/ByRef outputs, class initialization and control-flow merges invalidate
unsafe definitions. No unused literal or unproven `.Execute` receiver becomes an
execution fact. Statement links remain INFERRED or PARTIAL, never STATIC_PROVEN.

Parsing is capped at 2 MiB, 100,000 tokens and 64 parentheses nesting levels. SQL
recovery has 65,536-character / 128-fragment/separator budgets and a 50,000-fact
output budget. Version/grammar/dialect identifiers participate in registry scope
fingerprints. There is no ambient I/O, repository-global semantic catalog or cache.

Tests cover case/identity, class/property/parameter scopes, local shadowing,
CreateObject shadowing, aliases, ADODB options, dynamic dispatch, unsafe argument
side effects, unused/partial SQL, UTF-8/BOM/CRLF and parser budgets. PostgreSQL tests
exercise CLI-to-publication with Java/Groovy/PLPlus/BPMN, exact archived Evidence,
no-change reuse, file changes/deletion, descriptor-version invalidation, regenerated
fact equivalence and failed-attempt rollback preserving the prior pointer.

No GC, persistence or resolver changes are required for D12; it uses existing
source registry and immutable snapshot publication contracts.
