# Design: Аутентификация и разграничение прав MCP

## Context and current implementation
docs/server.md прямо сообщает об отсутствии аутентификации и ACL: доступный клиент читает любой опубликованный репозиторий.

## Proposed solution
### Decision 1
Определить boundary аутентификации для Streamable HTTP (проверяемый внешний issuer/proxy либо стандартный bearer token flow), fail-closed без identity.

### Decision 2
Разделить principal, repository membership и operation permission; хранить ACL в контролируемом хранилище или использовать надёжный авторизационный сервис.

### Decision 3
Принять request identity в stateless context; убрать возможность передавать произвольного пользователя в аргументах инструмента.

### Decision 4
Enforce authorization в общей точке до search/reader SQL; не полагаться на фильтрацию итогового ответа.

### Decision 5
Не раскрывать в ошибках названия недоступных репозиториев, source paths и fragments; предусмотреть аудит доступа.

## Integration and compatibility
- Reuse canonical UCM entities, immutable published snapshots and existing migration/adapter contracts.
- Keep existing public APIs compatible unless this change explicitly requires a versioned extension.
- Do not resolve cross-repository links during ingestion; expose deferred candidates only at query time.
- Every inferred relationship must retain Resolution, Coverage and Evidence; do not promote UNKNOWN to STATIC_PROVEN.

## Alternatives and trade-offs
- Avoid a broad rewrite or introducing a parallel storage model; targeted updates are easier to verify and roll back.
- If an optimization weakens referential integrity or snapshot immutability, reject it and preserve the current behavior.

## Failure modes and recovery
- Fail closed for invalid input, unknown ownership or missing permissions; report diagnostics without leaking source bytes.
- Database modifications require migration, backward-compatibility review and integration tests on PostgreSQL 15.
- A failed operation MUST leave the previously published snapshot readable and unchanged.

## Implementation surfaces
src/code_crawler/server.py; src/code_crawler/search.py; src/code_crawler/reader.py; src/code_crawler/migrations/; tests/test_server.py; tests/integration/; docs/server.md

## Dependencies
A01 не обязателен; опирается на текущий MCP/search API
