# Capability: database-qualified-search

## ADDED Requirements

### Requirement: Разделение режимов
The system MUST существующий API поиска по table/column оставить как синтаксический с явным mode в ответе.

#### Scenario: Разделение режимов
- GIVEN таблица orders встречается в двух БД
- WHEN вызывают SYNTACTIC_NAME
- THEN ответ явно помечен синтаксическим и может включать оба источника.

### Requirement: Физическая идентичность
The system MUST добавить параметры database_key, schema_version_key и database_object_id, валидировать совместимую комбинацию.

#### Scenario: Физическая идентичность
- GIVEN два объекта database1.public.orders и database2.public.orders
- WHEN указан database_object_id первого
- THEN возвращаются только доказанно привязанные обращения к нему.

### Requirement: Версионный контекст
The system MUST точный режим строить по RESOLVES_DATABASE_OBJECT/DatabaseAccess с проверкой контекста snapshot и schema version.

#### Scenario: Версионный контекст
- GIVEN versions V1/V2 одной БД
- WHEN указан version_key=V1
- THEN V2-accesses не выдаются как совпадения V1.

### Requirement: Quoted identifiers
The system MUST не включать UNRESOLVED или AMBIGUOUS в группу точных физических совпадений; вернуть их отдельно либо явно отразить coverage.

#### Scenario: Quoted identifiers
- GIVEN quoted имя "Users" и unquoted users
- WHEN запускают точный поиск
- THEN объекты не сливаются из-за lower().

### Requirement: Явная неполнота
The system MUST индексировать часто используемые фильтры после EXPLAIN на PG15.

#### Scenario: Явная неполнота
- GIVEN SQL access без назначенного connection
- WHEN выполняют exact поиск
- THEN он не превращается в resolved объект.

## Cross-cutting Requirements

### Requirement: Snapshot isolation and explainability
The change MUST preserve repository-scoped immutable published UCM facts and return Evidence/Coverage/Resolution for inferred relations.

#### Scenario: Failure does not modify current publication
- GIVEN an existing published snapshot
- WHEN this feature encounters an invalid input or a storage error
- THEN the publication pointer and previously published facts remain unchanged
