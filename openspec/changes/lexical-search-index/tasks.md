# Tasks

- [x] Document contract, ranking and limits (docs/lexical-search.md).
- [x] Migration 0019: pg_trgm, btree_gin, ucm_identifier_words, three GIN indexes.
- [x] search_text with filters, ranking and offset pagination; MCP tool search_text.
- [x] Integration tests: exact/words/similar, filters, pagination, snapshot scope, rejections.
- [x] Check plan, latency, index sizes and ingest cost on the load set.
- [x] Unit and integration suites pass (integration run on local PostgreSQL 18).
- [ ] Confirm on PostgreSQL 15 that the role may create pg_trgm and btree_gin.
- [ ] Prefix word matching and letter/digit word boundaries, if agents need them.
