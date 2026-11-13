# UCM legacy migration

## ADDED Requirements

### Requirement: Миграция без удаления рабочих данных
#### Scenario: Java/SQL index
- GIVEN legacy Java/PLPlus graph и checkout соответствующего commit.
- WHEN migrate_index выполняется.
- THEN создаётся validated published UCM snapshot и полный compatibility projection, legacy rows/IDs неизменны, read backend изначально legacy.

#### Scenario: Семантика SQL не повышается
- GIVEN legacy executes от неиспользованной SQL строки.
- WHEN graph мигрируется.
- THEN compatibility reader сохраняет прежнее ребро, SQL_CANDIDATE присутствует, подтверждённый canonical EXECUTES_SQL не создаётся; report содержит limitations.

### Requirement: Сравнение до переключения
#### Scenario: Совпадающие индексы
- GIVEN опубликованный compatible snapshot.
- WHEN compare_index и use_index(ucm) выполняются.
- THEN full graph/commit comparison успешен, чтение обоих backend эквивалентно.

#### Scenario: Legacy обновился
- GIVEN выбран UCM backend и затем legacy graph изменился.
- WHEN compare_index выполняется.
- THEN matches=false; UCM продолжает читать прежний snapshot.
- WHEN backend возвращается к legacy.
- THEN виден новый graph, повторное переключение на несовпадающий UCM отклоняется.
- WHEN migrate_index выполняется повторно.
- THEN новый snapshot снова совпадает с legacy и может быть выбран.

### Requirement: Immutable projection
#### Scenario: Замороженные данные
- GIVEN migrated snapshot PUBLISHED.
- WHEN удаляются projection nodes.
- THEN guard отклоняет изменение.

### Requirement: Атомарность failure
#### Scenario: Source drift
- GIVEN legacy graph и изменившиеся checkout bytes.
- WHEN выполняется migration без предварительного index.
- THEN операция отклоняется, legacy rows и прежняя публикация сохранены.

#### Scenario: Projection COPY failure
- GIVEN прежний опубликованный snapshot.
- WHEN запись projection падает после canonical INSERT.
- THEN новые facts/projection откатываются, прежние legacy rows и pointer сохранены.

### Requirement: Полная совместимость PLPlus ответа
#### Scenario: Shared symbols, calls и data refs
- GIVEN PLPlus класс, операция NEW_AUTO, функция, запрос и вызов операции из другого файла.
- WHEN graph мигрируется и чтение переключается.
- THEN функции, calls, z# table refs и все node/edge/ref attrs сохраняются без потерь.

### Requirement: CLI workflow
#### Scenario: Управляемый переход
- GIVEN проинициализированная БД и legacy индекс.
- WHEN отдельные процессы выполняют migrate-index, compare-index, use-index ucm, show-index и use-index legacy.
- THEN все команды завершаются с 0 и выполняют выбранное действие.
- WHEN compare-index получает неизвестный repository key.
- THEN возвращается exit 1 с явной ошибкой.
