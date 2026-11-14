# Proposal: Аутентификация и разграничение прав MCP

## Why
docs/server.md прямо сообщает об отсутствии аутентификации и ACL: доступный клиент читает любой опубликованный репозиторий.

## Goal
Идентифицировать вызывающего клиента и проверять право чтения repository scope до любого доступа к UCM, Evidence и исходным байтам.

## Scope
- Определить boundary аутентификации для Streamable HTTP (проверяемый внешний issuer/proxy либо стандартный bearer token flow), fail-closed без identity.
- Разделить principal, repository membership и operation permission; хранить ACL в контролируемом хранилище или использовать надёжный авторизационный сервис.
- Принять request identity в stateless context; убрать возможность передавать произвольного пользователя в аргументах инструмента.
- Enforce authorization в общей точке до search/reader SQL; не полагаться на фильтрацию итогового ответа.
- Не раскрывать в ошибках названия недоступных репозиториев, source paths и fragments; предусмотреть аудит доступа.

## Non-goals
Не реализовывать собственную IdP и не открывать доступ к записи индекса через MCP.

## Dependencies
A01 не обязателен; опирается на текущий MCP/search API

## Impacted code
src/code_crawler/server.py; src/code_crawler/search.py; src/code_crawler/reader.py; src/code_crawler/migrations/; tests/test_server.py; tests/integration/; docs/server.md

## Priority
P0 до сетевой публикации

## Acceptance summary
1. Fail-closed authentication.
2. Repository-level ACL.
3. Source bytes protection.
4. Сохранение stateless модели.
5. Auditing.
