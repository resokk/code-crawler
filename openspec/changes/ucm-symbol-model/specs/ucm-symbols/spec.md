# UCM symbols

## ADDED Requirements

### Requirement: Различение перегрузок
Callable Symbol SHALL иметь ключ из owner, name и ordered parameter type names.

#### Scenario: Overload identity
- GIVEN методы с нулём параметров, int, String, int/String, String/int и другим владельцем.
- WHEN вычисляются ключи и ID.
- THEN ID различны, повторный расчёт стабилен, одинаковый qualified_name допустим, JSON roundtrip сохраняет модель.

#### Scenario: Return type и разрешение
- GIVEN одинаковые имена типов параметров с разными resolution и return_type.
- WHEN строятся callable keys.
- THEN ключи совпадают.

#### Scenario: Некорректная callable модель
- GIVEN отсутствующий owner/signature, несоответствующая ключу signature или signature у FIELD.
- WHEN валидируется Symbol.
- THEN документ отклоняется.

#### Scenario: Пустые части ключа
- GIVEN пустой owner или blank name.
- WHEN вызывается callable_key.
- THEN возвращается ошибка.

### Requirement: Типизированные декларации
#### Scenario: Некаллбэк символы и конструктор
- GIVEN CLASS, FIELD, PARAMETER, LOCAL_VARIABLE с TypeRef или CONSTRUCTOR с signature.
- WHEN выполняется JSON roundtrip.
- THEN вид и поля сохраняются.

### Requirement: Области видимости
#### Scenario: Вложенные области
- GIVEN FILE scope и дочерняя FILE/TYPE/CALLABLE/BLOCK scope с owner_symbol_id.
- WHEN выполняется JSON roundtrip.
- THEN ссылки на родителя и владельца сохранены.

### Requirement: Употребления и неразрешённые ссылки
#### Scenario: Виды occurrences
- GIVEN DECLARATION/REFERENCE/READ/WRITE/CALL с source_range и scope_id.
- WHEN сериализуется RESOLVED, UNRESOLVED или AMBIGUOUS occurrence.
- THEN координаты и resolution сохраняются; только RESOLVED содержит target.

#### Scenario: Противоречивый target
- GIVEN RESOLVED без target или UNRESOLVED/AMBIGUOUS с target.
- WHEN валидируется TypeRef или Occurrence.
- THEN документ отклоняется.

#### Scenario: Нет координат и области
- GIVEN Occurrence без source_range и scope_id.
- WHEN выполняется валидация.
- THEN документ отклоняется.

### Requirement: Совместимый экспорт схемы
#### Scenario: Расширение реестра
- GIVEN прежние CLASS/METHOD документы и новые типы EntityType.
- WHEN выполняется существующий набор entity tests.
- THEN прежние документы читаются, схема актуальна и дискриминатор покрывает весь реестр.
