# Tasks: Kotlin UCM symbols, calls and Java interoperability

- [x] 1. Review existing UCM, SourceAdapter, symbol resolution and incremental contracts.
- [x] 2. Define normative typed model, compatibility and detector version.
- [x] 3. Implement: Discover Kotlin .kt/.kts with explicit support and diagnostics for Kotlin scripts.
- [x] 4. Implement: Extract packages, imports, classes, interfaces, objects, functions, constructors, properties, scopes and occurrences.
- [x] 5. Implement: Handle overloads, extension functions, receivers, nullable types and generic signatures without false resolution.
- [x] 6. Implement: Resolve local Kotlin calls and supported Java interoperability via shared UCM symbols, preserving unknown targets.
- [x] 7. Implement: Integrate SQL construction/execution support for explicit supported Kotlin JDBC/Spring patterns and incremental invalidation.
- [x] 8. Create positive/negative fixture: Two overloaded Kotlin functions / indexing / they keep separate signature IDs
- [x] 9. Create positive/negative fixture: Extension function invocation / resolution / receiver and evidence are preserved without guessing missing types
- [x] 10. Create positive/negative fixture: Kotlin calls Java method in same repository / resolution / local CALLS relation is inferred only with sufficient evidence
- [x] 11. Create positive/negative fixture: Kotlin script uses unknown dynamic call / analysis / coverage PARTIAL and no fabricated definite target
- [x] 12. Test local reference resolving versus deferred cross-repository lookup.
- [x] 13. Add PostgreSQL 15 integration test from fixture to published UCM with Evidence and SourceAnalysis.
- [x] 14. Check idempotence and incremental invalidation when adapter fingerprint changes.
- [x] 15. Update language-specific docs and mark unsupported behavior in Coverage.
- [x] 16. Run ruff, unit, PG15 integration tests, and review regression results.

## Implementation notes

Normative v1 contract and unsupported behavior: `docs/kotlin-ucm.md`.
Uses existing canonical entities without schema changes; optional captured-inventory
preparation extends the registry for canonical Java symbol reuse. Kotlin/Java
catalog fingerprints conservatively invalidate the Kotlin adapter scope, including
negative dependencies from missing and newly ambiguous targets.

Validation: ruff check/format; full pytest with PostgreSQL 15; dedicated Kotlin
positive/negative tests and publication/full-versus-incremental roundtrip.
