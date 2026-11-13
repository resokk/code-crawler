# UCM data flow

## ADDED Requirements

### Requirement: Типизированные значения
Value SHALL сохранять вид значения, optional TypeRef и partial.

#### Scenario: Литералы
- GIVEN null, empty string, SQL string, int, finite float или bool.
- WHEN LITERAL проходит EntityDocument JSON roundtrip.
- THEN значение и точный scalar type сохранены.

#### Scenario: Неизвестное или символическое значение
- GIVEN UNKNOWN с partial=true или SYMBOLIC с любым partial и TypeRef.
- WHEN выполняется JSON roundtrip.
- THEN вид, тип и неполнота сохранены.

#### Scenario: Противоречивое значение
- GIVEN UNKNOWN без partial, payload у UNKNOWN/SYMBOLIC, partial у LITERAL, NaN, Infinity или dict payload.
- WHEN документ валидируется.
- THEN он отклоняется.

### Requirement: Минимальные операции
Operation SHALL иметь scope_id и упорядоченные ссылки на значения.

#### Scenario: Допустимые операции
- GIVEN READ с 0/1 входом/выходом, ASSIGN с 1/1, CONCAT с минимум 2/1, RETURN с 0–1/0 или CALL с любым числом входов и 0–1 выходом.
- WHEN выполняется roundtrip.
- THEN операция и порядок ссылок сохранены; повтор входа допустим.

#### Scenario: Недопустимый поток
- GIVEN нарушение кардинальности, повтор выходного ID или общий ID во входах и выходах.
- WHEN валидируется Operation.
- THEN документ отклоняется.

#### Scenario: Цель вызова
- GIVEN callee TypeRef.
- WHEN она добавлена к CALL.
- THEN сохраняется при roundtrip.
- WHEN она добавлена к READ.
- THEN операция отклоняется.

#### Scenario: Отсутствующая область или неправильная ссылка
- GIVEN CALL без scope_id или с некорректным value ID.
- WHEN валидируется документ.
- THEN он отклоняется.

### Requirement: Связная цепочка значений
#### Scenario: Динамическая конструкция
- GIVEN SQL literal и UNKNOWN parameter, SYMBOLIC результаты CONCAT и ASSIGN, затем CALL.
- WHEN документы сериализуются и загружаются.
- THEN выход CONCAT равен входу ASSIGN, выход ASSIGN равен входу CALL, порядок входов и partial сохранены.

### Requirement: Аддитивное расширение схемы
#### Scenario: Реестр и обратная совместимость
- GIVEN новые типы и прежние документы.
- WHEN выполняется весь набор контрактных тестов.
- THEN EntityDocument читает старые типы, экспорт совпадает с JSON Schema файлом и дискриминатор покрывает весь реестр.
