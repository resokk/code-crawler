# Tasks: VBScript symbols, calls and embedded SQL

- [ ] 1. Review existing UCM, SourceAdapter, symbol resolution and incremental contracts.
- [ ] 2. Define normative typed model, compatibility and detector version.
- [ ] 3. Implement: Integrate ANTLR VBScript grammar and parser diagnostics with SourceAdapter registry.
- [ ] 4. Implement: Extract sub/function declarations, parameters, class/method/property statements, scopes and explicit calls.
- [ ] 5. Implement: Detect static ADODB and SQL literal/build patterns without equating strings with execution.
- [ ] 6. Implement: Distinguish late-bound COM object methods and dynamic Eval/CreateObject calls as partial external references.
- [ ] 7. Implement: Preserve case-insensitive identifier semantics and byte-accurate source positions.
- [ ] 8. Create positive/negative fixture: Two differently cased VBScript references / resolution / case-insensitive lookup targets same symbol where unambiguous
- [ ] 9. Create positive/negative fixture: Function builds DELETE string without Execute / indexing / there is SQL candidate but no proven execution site
- [ ] 10. Create positive/negative fixture: ADODB.Connection.Execute with SQL text / analysis / execution sink and statement relation carry Evidence
- [ ] 11. Create positive/negative fixture: Late-bound COM dispatch / analysis / external selector remains partial with documented coverage
- [ ] 12. Test local reference resolving versus deferred cross-repository lookup.
- [ ] 13. Add PostgreSQL 15 integration test from fixture to published UCM with Evidence and SourceAnalysis.
- [ ] 14. Check idempotence and incremental invalidation when adapter fingerprint changes.
- [ ] 15. Update language-specific docs and mark unsupported behavior in Coverage.
- [ ] 16. Run ruff, unit, PG15 integration tests, and review regression results.
