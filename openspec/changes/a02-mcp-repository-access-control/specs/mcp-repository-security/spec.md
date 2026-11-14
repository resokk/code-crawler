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
