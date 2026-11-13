# UCM repository snapshots

## ADDED Requirements

### Requirement: Стабильная идентичность репозитория
#### Scenario: Basename не уникален
- GIVEN два разных repository_key с display_name=app.
- WHEN они регистрируются.
- THEN UUID различны, оба имени app сохраняются; повтор ключа возвращает прежний UUID.

#### Scenario: Конкурентная регистрация
- GIVEN два соединения PostgreSQL.
- WHEN одновременно регистрируется один ключ.
- THEN возвращается один UUID и в таблице одна строка.

#### Scenario: Некорректные metadata
- GIVEN blank repository_key/display_name/source или неизвестное поле.
- WHEN валидируется RepositoryInput.
- THEN запрос отклоняется.

### Requirement: Неизменяемая история metadata
#### Scenario: Повторный анализ
- GIVEN один commit с clean и dirty worktree, branch=null и source fingerprint.
- WHEN создаются два snapshots.
- THEN UUID различны, metadata сохранены, state BUILDING, publication отсутствует.

#### Scenario: Неизвестный repository
- GIVEN отсутствующий repository UUID.
- WHEN создаётся snapshot.
- THEN FK отклоняет INSERT.

#### Scenario: Некорректные snapshot metadata
- GIVEN blank commit/branch, неверный SHA-256 или строка вместо dirty bool.
- WHEN валидируется SnapshotInput.
- THEN документ отклоняется.

#### Scenario: Lifecycle и immutable поля
- GIVEN BUILDING snapshot.
- WHEN пропускается VALIDATING или изменяются commit/dirty/fingerprint/branch.
- THEN UPDATE отклоняется.
- WHEN последовательно устанавливаются VALIDATING, READY, PUBLISHED, RETIRED.
- THEN переходы успешны; возврат к предыдущему состоянию отклоняется.

### Requirement: Независимый publication pointer
#### Scenario: Новый snapshot не меняет чтение
- GIVEN pointer на старый snapshot.
- WHEN создаётся новый BUILDING snapshot.
- THEN published_snapshot по-прежнему возвращает старый.

#### Scenario: Принадлежность и удаление
- GIVEN snapshot repository A и repository B.
- WHEN B пытается сослаться на snapshot A или удаляется snapshot с pointer.
- THEN FK отклоняет операцию, прежний pointer остаётся.

### Requirement: Миграция без потери legacy
#### Scenario: Upgrade
- GIVEN применённые 0001/0002 и legacy repo/node.
- WHEN применяются недостающие миграции.
- THEN новые таблицы доступны, legacy rows сохранены, schema_state актуален.
