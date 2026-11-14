# Tasks: JavaScript and TypeScript UCM adapters

- [ ] 1. Review existing UCM, SourceAdapter, symbol resolution and incremental contracts.
- [ ] 2. Define normative typed model, compatibility and detector version.
- [ ] 3. Implement: Use separate versioned adapters for .js/.jsx and .ts/.tsx, with file-routing and TS project config.
- [ ] 4. Implement: Extract exports/imports, functions, classes, arrow functions, methods, variables, scopes, occurrences and type references.
- [ ] 5. Implement: Resolve local module paths, reexports and deterministic same-repository calls; dynamic imports/calls preserve uncertainty.
- [ ] 6. Implement: Capture supported fetch/axios HTTP client method/URL expressions as typed external API references.
- [ ] 7. Implement: Preserve TS overloads, generics and interface declarations without claiming runtime implementation.
- [ ] 8. Create positive/negative fixture: TS module imports another local module / indexing / reference target matches the correct file with Evidence
- [ ] 9. Create positive/negative fixture: JS dynamic import with variable path / resolution / target remains UNRESOLVED rather than arbitrary match
- [ ] 10. Create positive/negative fixture: Two TS overload signatures / indexing / symbols and callable occurrences remain distinguishable
- [ ] 11. Create positive/negative fixture: fetch call to remote REST endpoint / indexing / ExternalReference stores known method/path and dynamic portions as partial
- [ ] 12. Create positive/negative fixture: TS type-only import / analysis / type reference does not become definite runtime CALLS
- [ ] 13. Test local reference resolving versus deferred cross-repository lookup.
- [ ] 14. Add PostgreSQL 15 integration test from fixture to published UCM with Evidence and SourceAnalysis.
- [ ] 15. Check idempotence and incremental invalidation when adapter fingerprint changes.
- [ ] 16. Update language-specific docs and mark unsupported behavior in Coverage.
- [ ] 17. Run ruff, unit, PG15 integration tests, and review regression results.
