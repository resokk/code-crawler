# VBScript UCM adapter

`VbscriptSourceAdapter(dialect="postgres")` routes plaintext `.vbs` suffixes (all
ASCII case variants) through the captured-source registry. ANTLR 4.13.2 grammar v1
lives in `grammars/vbscript/VBScript.g4`; generated Python files are committed under
`src/code_crawler/vbscript/` and never edited by hand. No runtime source/COM/SQL,
network or ambient filesystem access occurs. Java is needed only for generation.

## Identity and supported syntax

Class, Sub, Function and Property Get/Let/Set declarations, parameters, Dim/Const
variables and explicit calls become existing Symbol/Scope/Occurrence/Operation
facts. A script class and `<run>` callable own top-level statements. Property accessors
are separate callable names (`property.get`, `.let`, `.set`), not inferred calls
from assignments. Symbol names/keys use Unicode casefold; occurrences and archived
source preserve spelling. Paths remain case-sensitive repository identities.

Lookup is lexical within the same file, with class scope and arity checks. Duplicate
case-insensitive declarations are diagnostics, never an arbitrary winner. Other
files are not implicitly loaded into one VBScript global environment: WSH/ASP host
composition and dynamic includes are unsupported. Unknown calls become deferred
ExternalReference selectors, with original source Evidence. Local unique calls are
RESOLVED/INFERRED, not runtime-proven. Eval/Execute/ExecuteGlobal/GetRef prevent
unconditional local dispatch resolution and invalidate local value assumptions.

## SQL and object flow

Strings use VBScript doubled-quote escaping; `&` concatenation, `+` when all
operands are known strings, and local
straight-line assignments recover SQL constructions/fragments. Dynamic pieces are
explicit partial fragments; statement-local SQL semantics reuse SQLGlot for the
configured postgres/mysql/tsql dialect. Partial constructions assert no accesses.
Unused SQL literals/builds have candidates but no execution relation.

ADODB.Connection.Execute and ADODB.Recordset.Open require receiver provenance from
literal, unversioned CreateObject ProgIDs from this three-type allowlist. ADODB.Command.Execute additionally requires captured
CommandText and CommandType=1 (adCmdText). Known non-text command options do not
produce an SQL statement binding. Receiver aliases are tracked locally; rebinding,
unknown ByRef calls, branching/loops and dynamic code discard unsafe assumptions.
A variable called `conn`, or an arbitrary COM method called Execute, proves nothing.
Execution-site/statement links carry Evidence and INFERRED certainty; COM dispatch
itself stays an unresolved external dependency. No database object identity is guessed.

## Diagnostics, coverage and lifecycle

All analysis capabilities except successful grammar diagnostics are PARTIAL:
Variant types, property/default-member dispatch, ByRef/interprocedural mutation,
runtime COM binding, host composition and nontrivial control/data flow are not
resolved. Syntax/encoding/duplicate-declaration/complexity errors fail analysis with
structured path/range diagnostics, roll back the attempt and retain the previously
published snapshot. Captured bytes must be UTF-8 without NUL; an initial BOM is accepted. Limits are 2 MiB,
100,000 tokens and 64 parenthesis nesting levels per file; recursion failure also
becomes a diagnostic. Recovery is additionally bounded to 65,536 characters,
128 fragments/separators per expression/candidate and 50,000 output facts per file.
Budget violations abort the attempt. No guessed facts are published after parser recovery.

Descriptor/analyzer/grammar/dialect versions participate in registry fingerprints.
Facts depend only on their own file; no-change indexing reuses them, and version
changes invalidate the VBScript scope using existing incremental contracts. Mixed
Java/Groovy/PLPlus/BPMN routing and snapshot publication/evidence remain centralized.

Additional unsupported surfaces include WSF/ASP host containers/includes, ADODB
parameter binding/lineage, array/default-member flow, implicit property invocation
and interprocedural return-value recovery. Their absence does not imply no dependency:
unknown explicit calls remain external, and all affected analysis capabilities are
PARTIAL with bounded-profile reasons. Changes to grammar/recovery semantics require
an adapter/analysis version bump so existing snapshots are not silently reused.
