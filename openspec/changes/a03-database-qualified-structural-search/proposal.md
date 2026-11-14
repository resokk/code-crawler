# Proposal: Точный поиск SQL-доступов в контексте физической БД

## Why
search._accesses фильтрует по нормализованным SQL-именам, не по database_key/version_key/DATABASE_OBJECT; одноимённые таблицы из разных БД смешиваются.

## Goal
Добавить явные режимы SYNTACTIC_NAME и RESOLVED_DATABASE_OBJECT; сохранять неопределённость и происхождение результата.

## Scope
- Существующий API поиска по table/column оставить как синтаксический с явным mode в ответе.
- Добавить параметры database_key, schema_version_key и database_object_id, валидировать совместимую комбинацию.
- Точный режим строить по RESOLVES_DATABASE_OBJECT/DatabaseAccess с проверкой контекста snapshot и schema version.
- Не включать UNRESOLVED или AMBIGUOUS в группу точных физических совпадений; вернуть их отдельно либо явно отразить coverage.
- Индексировать часто используемые фильтры после EXPLAIN на PG15.

## Non-goals
Не угадывать контексты подключения; не изменять SQL анализатор и не делать cross-repo resolution.

## Dependencies
Существующие database identity и structural search

## Impacted code
src/code_crawler/search.py; src/code_crawler/server.py; src/code_crawler/database_resolution.py; tests/integration/test_structural_search.py; docs/structural-search.md

## Priority
P1

## Acceptance summary
1. Разделение режимов.
2. Физическая идентичность.
3. Версионный контекст.
4. Quoted identifiers.
5. Явная неполнота.
