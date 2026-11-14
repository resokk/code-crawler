# Tasks: Persistent OpenSpec history and change dependencies

- [ ] 1. Review current docs and migration/observability or retention implementations; reproduce missing behavior.
- [ ] 2. Define minimal interfaces and durable typed contracts.
- [ ] 3. Implement: Define active openspec/changes versus completed openspec/changes/archive and a stable naming convention.
- [ ] 4. Implement: After implementation + CI + acceptance, archive proposal/design/specs/tasks with completion receipt and commit/CI link.
- [ ] 5. Implement: Maintain roadmap with dependencies, current baseline SHA, priority and explicit open criteria.
- [ ] 6. Implement: Provide agent execution instructions: implement one change at a time, do not invent new capabilities, preserve tests/docs, stop at scope boundary.
- [ ] 7. Implement: Handle superseded specs by linking replacements and archiving instead of deleting evidence of design decisions.
- [ ] 8. Add positive and negative acceptance test: Change fully implemented and tests passed / archiving / its proposal/design/specs/tasks remain accessible under archive
- [ ] 9. Add positive and negative acceptance test: Open checkboxes remain / attempting archive / change stays active until tests/criteria are verified
- [ ] 10. Add positive and negative acceptance test: LLM starts feature / reading roadmap / dependencies and single-change scope are explicit
- [ ] 11. Add positive and negative acceptance test: Existing historical changes removed earlier / recovering history / Git source is preserved without silently claiming completion
- [ ] 12. Verify snapshot pointer immutability and evidence availability after failure/recovery.
- [ ] 13. Add PostgreSQL 15 integration or operator runbook validation when relevant.
- [ ] 14. Document constraints, security boundaries and explicit Coverage.
- [ ] 15. Run ruff, pytest --require-postgres, CI and failure-injection suite; archive only after all checks pass.
