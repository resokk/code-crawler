# UCM entities

## ADDED Requirements

### Requirement: Версионированный строгий envelope
Сущности SHALL содержать contract_version=1, repository_id, logical_key, entity_type, id и непустое name. Неизвестные поля SHALL отклоняться.

#### Scenario: Базовые сущности
- GIVEN CLASS, METHOD и SQL_CANDIDATE с корректным ID и координатами.
- WHEN документ сериализуется и загружается.
- THEN тип и поля сохраняются без потерь.

#### Scenario: Некорректные поля
- GIVEN несовпадающий ID, версия 2, пустое имя или лишнее поле.
- WHEN выполняется валидация.
- THEN документ отклоняется.

### Requirement: Детерминированная логическая идентичность
ID SHALL вычисляться по формату docs/ucm.md, с явным repository scope.

#### Scenario: Стабильность и разделение
- GIVEN фиксированные Unicode-компоненты ключа.
- WHEN вычисляется ID.
- THEN он совпадает с SHA-256 нормативного JSON; изменение scope, типа или ключа меняет ID.

### Requirement: SourceFile имеет типизированные свойства
#### Scenario: Roundtrip и изменение содержимого
- GIVEN относительный POSIX path, язык и SHA-256 bytes.
- WHEN SourceFile проходит JSON roundtrip и меняется только content hash.
- THEN поля сохраняются, logical ID остаётся прежним, модель запрещает присваивание полей.

#### Scenario: Некорректный путь или hash
- GIVEN абсолютный путь, traversal, пустой сегмент, backslash, NUL, drive prefix, несовпадающий logical_key или неправильный hash.
- WHEN строится SourceFile.
- THEN валидатор отклоняет документ.

### Requirement: Единые координаты исходников
#### Scenario: Некорректная позиция
- GIVEN строка меньше 1, отрицательная колонка, boolean или строка вместо числа.
- WHEN создаётся Position.
- THEN валидация завершается ошибкой.

#### Scenario: Полуоткрытый диапазон
- GIVEN позиции start и end в одном файле.
- WHEN end равен start.
- THEN пустой диапазон допустим.
- WHEN end предшествует start.
- THEN диапазон отклоняется.

### Requirement: Экспортируемая схема
#### Scenario: Проверка артефакта и реестра
- GIVEN текущие модели и EntityType registry.
- WHEN экспортируется entity_json_schema().
- THEN результат совпадает с версионируемым JSON-файлом, дискриминатор покрывает все типы, дополнительные поля запрещены.
