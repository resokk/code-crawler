# Tasks: GraphQL SDL and introspection schema adapter

- [ ] 1. Review existing UCM, SourceAdapter, symbol resolution and incremental contracts.
- [ ] 2. Define normative typed model, compatibility and detector version.
- [ ] 3. Implement: Discover .graphql/.graphqls/.gql SDL and supported introspection JSON sources.
- [ ] 4. Implement: Parse local schema definitions and type/schema extensions into consistent composed schema, with source provenance.
- [ ] 5. Implement: Model SCALAR, OBJECT, INPUT_OBJECT, ENUM, INTERFACE, UNION, field arguments and exact list/non-null modifiers.
- [ ] 6. Implement: Extract actual Query/Mutation/Subscription root type fields, custom root names, directives and deprecations.
- [ ] 7. Implement: Preserve unknown federation extensions and unresolved schema components without runtime GraphQL execution.
- [ ] 8. Create positive/negative fixture: Schema uses custom root type RootQuery / parsing / root operation fields reflect RootQuery rather than assuming Query
- [ ] 9. Create positive/negative fixture: SDL with type and extend type in two files / composition / one type exposes all fields with per-source evidence
- [ ] 10. Create positive/negative fixture: Field returns list of non-null Loan within non-null list / normalizing / all nested modifiers are retained
- [ ] 11. Create positive/negative fixture: Introspection JSON lacks SDL coordinates / normalizing / source position is explicitly unavailable rather than fabricated
- [ ] 12. Create positive/negative fixture: Undefined referenced type / validation / diagnostics and partial coverage are returned
- [ ] 13. Test local reference resolving versus deferred cross-repository lookup.
- [ ] 14. Add PostgreSQL 15 integration test from fixture to published UCM with Evidence and SourceAnalysis.
- [ ] 15. Check idempotence and incremental invalidation when adapter fingerprint changes.
- [ ] 16. Update language-specific docs and mark unsupported behavior in Coverage.
- [ ] 17. Run ruff, unit, PG15 integration tests, and review regression results.
