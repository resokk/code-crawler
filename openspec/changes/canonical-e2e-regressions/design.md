# Design

Use isolated PostgreSQL 15 and local committed Java/Groovy/PLPlus fixture sources.
Run canonical CLI then read the selected snapshot with the typed reader. Assert
calls, SQL constructions/executions/accesses/bindings and source archive content.
Exercise no-change indexing and injected publication failure without mocking away
storage/lifecycle transactions. Restore proofs after checkout deletion.
