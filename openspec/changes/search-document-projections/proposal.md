# Search document projections

Full-text and vector search need text, but UCM facts are structured rows. Add
deterministic generators that turn Java symbols, SQL statements, database objects,
call graph summaries and the facts of other adapters into documents built from UCM
only. No storage, embeddings or retrieval in this change.
