# UCM publication

## ADDED Requirements

### Requirement: Readiness подтверждается содержимым storage
#### Scenario: Корректный snapshot
- GIVEN полный batch, загруженный в BUILDING.
- WHEN validate_snapshot вызывается дважды.
- THEN создаётся один immutable receipt, возвращается entity count и состояние READY; pointer ещё отсутствует.

#### Scenario: Неполный или некорректный storage
- GIVEN отсутствующий subtype/evidence/coverage reason/candidate, неверная operation cardinality, gap ordinal, неподходящая TypeRef role, несовпадающий logical ID, scope cycle или отсутствующая occurrence location.
- WHEN вызывается validation.
- THEN READY и receipt не создаются, snapshot остаётся VALIDATING, прежняя публикация сохранена.

#### Scenario: Ошибка перед receipt
- GIVEN корректный frozen snapshot и SQL failure при INSERT receipt.
- WHEN validation завершается ошибкой.
- THEN receipt отсутствует, facts сохранены, состояние VALIDATING.
- WHEN ошибка устранена.
- THEN повтор validation и publication успешны.

#### Scenario: Параллельная validation
- GIVEN два соединения проверяют один snapshot.
- WHEN оба вызова завершаются.
- THEN count одинаков, receipt один.

### Requirement: Атомарное переключение
#### Scenario: Последовательные публикации
- GIVEN READY old/new snapshots.
- WHEN old публикуется, затем new с expected=old.
- THEN pointer указывает new, old RETIRED, new PUBLISHED, оба набора facts сохранены.

#### Scenario: Ошибка SQL или cancellation
- GIVEN опубликованный old и READY new.
- WHEN переключение падает или отменяется во время pointer UPDATE после изменения states.
- THEN старый pointer и PUBLISHED state сохранены, new остаётся READY, retry успешен.

#### Scenario: MVCC reader
- GIVEN транзакция переключения остановлена перед pointer UPDATE.
- WHEN другое соединение читает publication.
- THEN оно видит old PUBLISHED и new READY; после успешного commit видит new.

### Requirement: Защита конкурирующих публикаций
#### Scenario: Два новых target одного репозитория
- GIVEN два READY target и одинаковый expected pointer.
- WHEN два соединения публикуют одновременно.
- THEN один успех, второй stale-pointer error; только один PUBLISHED, проигравший target остаётся READY.

#### Scenario: Разные репозитории
- GIVEN по READY snapshot в двух repositories.
- WHEN они публикуются параллельно.
- THEN обе операции успешны.

### Requirement: Явный rollback
#### Scenario: Восстановление прежнего snapshot
- GIVEN old RETIRED после публикации new.
- WHEN rollback_publication вызывается с target old и expected new.
- THEN old снова PUBLISHED, new RETIRED, pointer указывает old, facts неизменны.

#### Scenario: Повтор и stale expectation
- GIVEN уже выбранный PUBLISHED target.
- WHEN повторяется публикация с expected target.
- THEN результат безопасен.
- WHEN используется старый/неверный expected pointer.
- THEN операция отклоняется.

### Requirement: Ограничения API и SQL
#### Scenario: Недопустимая публикация
- GIVEN BUILDING target, неизвестный repository/snapshot, target другого repository или активная внешняя transaction.
- WHEN вызывается API.
- THEN операция отклоняется без изменения публикации.

#### Scenario: SQL invariants
- GIVEN VALIDATING без receipt, READY без pointer либо PUBLISHED с pointer.
- WHEN SQL пытается обойти READY receipt gate, создать PUBLISHED без pointer, pointer на READY, удалить pointer, retire без переключения, изменить receipt или TRUNCATE metadata.
- THEN transaction отклоняется.
