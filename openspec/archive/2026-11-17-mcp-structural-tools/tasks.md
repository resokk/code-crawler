# Tasks

- [x] Document tools and rules (docs/server.md).
- [x] Pool in server lifespan; read-only transaction per call.
- [x] Eight tools with typed, validated arguments and docstrings.
- [x] Unit tests without a database: tool list, argument passing, validation, error mapping.
- [x] Integration test: tools through an MCP client against a published snapshot.
- [x] Unit and integration suites pass (integration run on local PostgreSQL 18).
- [x] Integration suite on PostgreSQL 15.
- [ ] Access control (repository-access-control, R6).

Verified by [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43612670068) at `e8e5f18` (842 tests passed).
