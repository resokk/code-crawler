# UCM core storage

## ADDED Requirements

### Requirement: Нормализованные канонические факты
#### Scenario: Базовый граф
- GIVEN BUILDING snapshot и envelope/subtype rows для файла, символа, scope, occurrence, operation, value, relation и external reference.
- WHEN транзакция фиксируется.
- THEN все восемь сущностей, literal, type ref, два повторных ordered inputs и evidence доступны в соответствующих таблицах; пустая external signature остаётся пустым массивом.

### Requirement: Реестр типов отношений
#### Scenario: SQL registry соответствует UCM
- GIVEN матрица в миграции и Python relation_registry().
- WHEN сравниваются пары kind/source_type/target_type.
- THEN множества совпадают.

#### Scenario: Неверные endpoints
- GIVEN CONSUMES с SYMBOL target или candidate.
- WHEN выполняется запись.
- THEN FK отклоняет пару.

### Requirement: Изоляция snapshots и repositories
#### Scenario: Ссылка в другой snapshot
- GIVEN заполненный snapshot A и новый B.
- WHEN OPERATION в B ссылается на scope, существующий только в A.
- THEN deferred FK отклоняет транзакцию.
- WHEN полный граф загружается в B.
- THEN одинаковый logical ID хранится независимо в обоих snapshots.

#### Scenario: Неверный repository
- GIVEN snapshot repository A.
- WHEN entity указывает repository B.
- THEN composite FK отклоняет INSERT.

### Requirement: Discriminator соответствует subtype
#### Scenario: SYMBOL записан как VALUE
- GIVEN envelope типа SYMBOL.
- WHEN для него добавляется ucm_values row.
- THEN deferred FK отклоняет транзакцию.

### Requirement: Доменные ограничения
#### Scenario: Неверные ranges и payload
- GIVEN обратный evidence range либо JSON object literal.
- WHEN обновляется каноническая строка.
- THEN CHECK отклоняет изменение.

#### Scenario: Путь выходит за root
- GIVEN SOURCE_FILE с traversal path.
- WHEN обновляется path.
- THEN CHECK отклоняет изменение.

#### Scenario: Resolution и selector
- GIVEN occurrence с UNRESOLVED и target либо external SYMBOL selector с HTTP полями.
- WHEN строка обновляется.
- THEN CHECK отклоняет изменение.

### Requirement: Immutable snapshot content
#### Scenario: Замороженный snapshot
- GIVEN snapshot в VALIDATING/READY/PUBLISHED/RETIRED.
- WHEN выполняется fact INSERT/UPDATE/DELETE или TRUNCATE.
- THEN запись запрещена, существующий граф сохранён.

#### Scenario: Запрет переноса и TRUNCATE CASCADE
- GIVEN канонический граф в BUILDING snapshot.
- WHEN меняется snapshot_id fact или TRUNCATE CASCADE любой fact/support table.
- THEN операция отклоняется и данные сохранены.

#### Scenario: State transition ждёт writer
- GIVEN открытая транзакция записи факта.
- WHEN второе соединение меняет state с коротким lock_timeout.
- THEN оно получает LockNotAvailable до завершения writer.
- WHEN writer фиксируется.
- THEN state transition успешен, последующая запись запрещена.

### Requirement: Совместимая migration
#### Scenario: Полный regression suite
- GIVEN legacy schema/data и прежние CLI/COPY tests.
- WHEN применены все migrations, включая 0004.
- THEN upgrade сохраняет legacy rows и все прежние integration tests проходят.
