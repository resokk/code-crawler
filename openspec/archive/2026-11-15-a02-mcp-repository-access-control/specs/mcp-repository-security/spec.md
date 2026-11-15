# Capability: mcp-repository-security

## ADDED Requirements

### Requirement: Fail-closed authentication
The system MUST определить boundary аутентификации для Streamable HTTP (проверяемый внешний issuer/proxy либо стандартный bearer token flow), fail-closed без identity.

#### Scenario: Fail-closed authentication
- GIVEN запрос MCP без действительной аутентификации
- WHEN вызывают любой tool
- THEN доступ отклоняется до запроса к UCM.

### Requirement: Repository-level ACL
The system MUST разделить principal, repository membership и operation permission; хранить ACL в контролируемом хранилище или использовать надёжный авторизационный сервис.

#### Scenario: Repository-level ACL
- GIVEN principal имеет доступ к repo A, но не B
- WHEN он ищет symbols или SQL в B
- THEN данные и Evidence B не выдаются.

### Requirement: Source bytes protection
The system MUST принять request identity в stateless context; убрать возможность передавать произвольного пользователя в аргументах инструмента.

#### Scenario: Source bytes protection
- GIVEN principal не имеет доступа к repo
- WHEN запрашивает archived source fragment через любой путь
- THEN содержимое не выдаётся.

### Requirement: Сохранение stateless модели
The system MUST enforce authorization в общей точке до search/reader SQL; не полагаться на фильтрацию итогового ответа.

#### Scenario: Сохранение stateless модели
- GIVEN два параллельных запроса разных principals
- WHEN сервер обрабатывает запросы
- THEN нет межзапросной утечки прав, и сервер не хранит пользовательскую сессию.

### Requirement: Auditing
The system MUST не раскрывать в ошибках названия недоступных репозиториев, source paths и fragments; предусмотреть аудит доступа.

#### Scenario: Auditing
- GIVEN разрешённый или отклонённый запрос
- WHEN завершена авторизационная проверка
- THEN событие аудита сохраняется без сырых секретов.

## Cross-cutting Requirements

### Requirement: Snapshot isolation and explainability
The change MUST preserve repository-scoped immutable published UCM facts and return Evidence/Coverage/Resolution for inferred relations.

#### Scenario: Failure does not modify current publication
- GIVEN an existing published snapshot
- WHEN this feature encounters an invalid input or a storage error
- THEN the publication pointer and previously published facts remain unchanged

### Requirement: Operation permission and membership are independent
The server MUST require both repository membership and the operation permission
before acquiring a query connection.

#### Scenario: Membership without permission
- GIVEN an authenticated principal belongs to a repository but lacks read, evidence or discover permission
- WHEN the corresponding tool is called
- THEN access is denied before acquiring a database connection.

### Requirement: Discovery scope is intersected before retrieval
The server MUST intersect deployment discovery scope with principal membership.

#### Scenario: A client requests a foreign discovery scope
- GIVEN principal A can read only repository A and deployment scope contains A and B
- WHEN A requests discovery for B
- THEN the request is denied before retrieval and B is not named in the error.

### Requirement: Source evidence has an authorized library entry point
The authorized source Evidence reader MUST verify request credentials and source
permission before opening the canonical reader.

#### Scenario: Caller-supplied identity claims cannot grant source access
- GIVEN a token for A with a client_id claim naming B
- WHEN authorized_evidence requests repository B
- THEN the token resolves to A and access is denied before source retrieval.

### Requirement: Expiration and configuration fail closed
The server MUST reject expired credentials and invalid deployment policy without
including validation inputs in the diagnostic.

#### Scenario: An expired bearer requests a tool
- GIVEN the bearer digest exists but its expires_at has passed
- WHEN the request authenticates
- THEN it is denied and no UCM retrieval occurs.

### Requirement: Cross-repository context never grants authority
Cross-repository traversal MUST require read/discover permissions and membership
within deployment scope for the root and every selected repository before SQL.

#### Scenario: Context includes a forbidden repository
- GIVEN a principal can read only repository A
- WHEN it requests traversal with root A and a context selecting A and B
- THEN access is denied before obtaining a database connection.

#### Scenario: A context disguises another repository snapshot
- GIVEN a principal can read only repository A
- WHEN a context labels repository B snapshot identifiers as A
- THEN ownership verification rejects retrieval and the tool returns a redacted error.
