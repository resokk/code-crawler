# Tasks

- [x] Document contract, ranking and limits (docs/lexical-search.md).
- [x] Migration 0019: pg_trgm, btree_gin, ucm_identifier_words, three GIN indexes.
- [x] search_text with filters, ranking and offset pagination; MCP tool search_text.
- [x] Integration tests: exact/words/similar, filters, pagination, snapshot scope, rejections.
- [x] Check plan, latency, index sizes and ingest cost on the load set.
- [x] Unit and integration suites pass (integration run on local PostgreSQL 18).
- [x] Confirm on PostgreSQL 15 that the role may create pg_trgm and btree_gin.
- [ ] Prefix word matching and letter/digit word boundaries, if agents need them.

Verified by [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43612670068) at `e8e5f18` (842 tests passed).

Extension creation is verified for the CI test role; production-role permissions are deployment-specific.
