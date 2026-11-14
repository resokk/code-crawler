# Tasks: GraphQL Java resolver and DataFetcher bindings

- [ ] 1. Review existing UCM, SourceAdapter, symbol resolution and incremental contracts.
- [ ] 2. Define normative typed model, compatibility and detector version.
- [ ] 3. Implement: Support Spring GraphQL QueryMapping, MutationMapping, SubscriptionMapping, SchemaMapping and BatchMapping.
- [ ] 4. Implement: Resolve typed field identity including owner type, field name, argument types and return types.
- [ ] 5. Implement: Detect supported GraphQL Java DataFetcher registration and DGS profiles, with version-specific capabilities.
- [ ] 6. Implement: Treat default property/data fetching as possible but not a fictitious handler; ambiguous resolvers remain uncertain.
- [ ] 7. Implement: Link field→local Java symbol→existing CALLS→SQL without reparsing SQL; preserve deferred external target references.
- [ ] 8. Create positive/negative fixture: Mutation createLoan matches one Java MutationMapping / analysis / root operation links to method with evidence
- [ ] 9. Create positive/negative fixture: Loan.repaymentSchedule field has SchemaMapping / analysis / nested field links to resolver and onward to SQL through CALLS
- [ ] 10. Create positive/negative fixture: Two compatible resolvers for one field / resolution / AMBIGUOUS with candidates is returned
- [ ] 11. Create positive/negative fixture: No explicit resolver uses default getter semantics / analysis / no fake Java resolver relation is emitted
- [ ] 12. Create positive/negative fixture: External federated subgraph / indexing / deferred selector rather than global read
- [ ] 13. Test local reference resolving versus deferred cross-repository lookup.
- [ ] 14. Add PostgreSQL 15 integration test from fixture to published UCM with Evidence and SourceAnalysis.
- [ ] 15. Check idempotence and incremental invalidation when adapter fingerprint changes.
- [ ] 16. Update language-specific docs and mark unsupported behavior in Coverage.
- [ ] 17. Run ruff, unit, PG15 integration tests, and review regression results.
