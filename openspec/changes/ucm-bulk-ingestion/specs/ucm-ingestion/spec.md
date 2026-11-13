# UCM batch ingestion

## ADDED Requirements

### Requirement: Замкнутый batch одного репозитория
#### Scenario: Некорректные ссылки
- GIVEN duplicate ID, отсутствующий файл/scope/TypeRef target, Value ref неправильного типа, foreign repository, два producers одного Value или parent_scope cycle.
- WHEN строится UcmBatch.
- THEN validation отклоняет batch до записи.

#### Scenario: JSON roundtrip и пустой batch
- GIVEN корректный batch с обратным порядком entities либо пустой batch.
- WHEN выполняется JSON roundtrip.
- THEN модели и порядок сохраняются, empty batch допустим.

### Requirement: Полная двухпроходная загрузка
#### Scenario: Все типы UCM
- GIVEN batch с forward refs, cyclic symbol/scope ownership, signature, TypeRefs, operation values, partial Relation/candidate, evidence, coverage и всеми external selectors.
- WHEN вызывается ingest_batch.
- THEN строки доступны в нормализованных таблицах, logical→physical mapping полон, state остаётся BUILDING и staging удалён.
- AND сохраняются parameter order, повторные inputs, JSON null/Unicode, nonliteral SQL NULL, unknown/empty signature, selector case и unresolved semantics.

#### Scenario: Scalar literals
- GIVEN int, finite float, bool либо empty string LITERAL.
- WHEN batch загружается COPY.
- THEN literal сохраняет значение и scalar type.

### Requirement: Явные границы writer
#### Scenario: Неверный snapshot или состояние
- GIVEN отсутствующий snapshot, repository mismatch, непустой snapshot либо snapshot не BUILDING.
- WHEN запускается загрузка.
- THEN writer отклоняет операцию.

#### Scenario: Внешняя транзакция или обход model validation
- GIVEN активная внешняя transaction либо UcmBatch, изменённый через model_copy с duplicate ID.
- WHEN вызывается ingest_batch.
- THEN writer отклоняет операцию и не добавляет фактов.

### Requirement: Атомарность и повтор после ошибки
#### Scenario: Ошибка COPY или canonical INSERT
- GIVEN прежний опубликованный snapshot и новый пустой BUILDING snapshot.
- WHEN COPY отклоняет NUL либо canonical INSERT падает после переноса envelopes.
- THEN новый snapshot пуст, staging удалён, transaction закрыта, прежний граф и pointer сохранены.
- WHEN причина ошибки устранена и повторяется загрузка.
- THEN batch успешно загружается в тот же новый snapshot.

#### Scenario: Cancellation во время canonical write
- GIVEN writer, заблокированный в evidence INSERT.
- WHEN asyncio task отменяется.
- THEN transaction и canonical rows откатываются, staging удалён, retry успешен.

### Requirement: Конкурентная загрузка
#### Scenario: Один snapshot
- GIVEN два соединения и один пустой snapshot.
- WHEN одновременно загружается одинаковый batch.
- THEN один writer успешен, второй получает ошибку непустого snapshot, дубликатов нет.

#### Scenario: Разные snapshots
- GIVEN два пустых snapshots.
- WHEN batches загружаются параллельно.
- THEN обе загрузки успешны и независимы.
