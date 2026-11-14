# Tasks: Kotlin UCM symbols, calls and Java interoperability

- [ ] 1. Review existing UCM, SourceAdapter, symbol resolution and incremental contracts.
- [ ] 2. Define normative typed model, compatibility and detector version.
- [ ] 3. Implement: Discover Kotlin .kt/.kts with explicit support and diagnostics for Kotlin scripts.
- [ ] 4. Implement: Extract packages, imports, classes, interfaces, objects, functions, constructors, properties, scopes and occurrences.
- [ ] 5. Implement: Handle overloads, extension functions, receivers, nullable types and generic signatures without false resolution.
- [ ] 6. Implement: Resolve local Kotlin calls and supported Java interoperability via shared UCM symbols, preserving unknown targets.
- [ ] 7. Implement: Integrate SQL construction/execution support for explicit supported Kotlin JDBC/Spring patterns and incremental invalidation.
- [ ] 8. Create positive/negative fixture: Two overloaded Kotlin functions / indexing / they keep separate signature IDs
- [ ] 9. Create positive/negative fixture: Extension function invocation / resolution / receiver and evidence are preserved without guessing missing types
- [ ] 10. Create positive/negative fixture: Kotlin calls Java method in same repository / resolution / local CALLS relation is inferred only with sufficient evidence
- [ ] 11. Create positive/negative fixture: Kotlin script uses unknown dynamic call / analysis / coverage PARTIAL and no fabricated definite target
- [ ] 12. Test local reference resolving versus deferred cross-repository lookup.
- [ ] 13. Add PostgreSQL 15 integration test from fixture to published UCM with Evidence and SourceAnalysis.
- [ ] 14. Check idempotence and incremental invalidation when adapter fingerprint changes.
- [ ] 15. Update language-specific docs and mark unsupported behavior in Coverage.
- [ ] 16. Run ruff, unit, PG15 integration tests, and review regression results.
