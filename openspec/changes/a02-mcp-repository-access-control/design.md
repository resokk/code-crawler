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

## Implemented boundary

The existing FastMCP TokenVerifier interface validates opaque bearer credentials
against SHA-256 digests in deployment-owned MCP_ACCESS_POLICY. Principals, explicit
repository memberships and read/evidence/source/discover permissions are immutable
models; expiration is checked for every request. No identity tool parameter or
forwarded user header is trusted. Missing/malformed policy prevents startup.

The common server _query gate revalidates request credentials and authorizes scope
before acquiring a DB connection. Discovery intersects principal membership and
server scope before constructing its callback. Library authorized_evidence checks
source permission before opening the canonical reader. Raw database/library APIs
remain privileged administrative interfaces, not HTTP entry points.

HTTP authentication failures and authorization decisions use structured redacted
audit logs. Operators collect stderr into their persistent restricted sink. Tool
query errors are generic; errors contain no inaccessible names, paths or fragments.
No session grant cache, PostgreSQL ACL schema or new migration is needed. Policy
rotation is deployment controlled and requires consistent worker restart; an IdP,
online membership administration and durable audit storage service are not added.

Tests use native ASGI HTTP authentication and PostgreSQL 15, including two
concurrent identities with disjoint repository scopes across every registered
tool, source Evidence restoration, denied operations before DB access and masked
DB exception text. Existing in-process tool tests opt into explicit test identity;
production in-process calls without identity remain denied.

The C06 MCP traversal added on main is covered by the same boundary: read and
discover permissions plus membership/server scope for the root and every context
selection are checked before acquiring a connection. Forged context snapshot IDs
remain subject to the existing repository ownership checks and masked errors.
