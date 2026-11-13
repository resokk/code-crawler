# UCM external references

## ADDED Requirements

### Requirement: Независимый неразрешённый факт
ExternalReference SHALL сохранять selector, локальный source, reason, evidence, certainty и coverage без внешнего индекса.

#### Scenario: Типизированные selectors
- GIVEN SYMBOL с неизвестной/пустой/непустой сигнатурой, HTTP или DATABASE selector и hints.
- WHEN документ проходит JSON roundtrip и локальную проверку.
- THEN поля и UNRESOLVED сохраняются; каталог содержит только локальные source/file.

#### Scenario: Неизвестная сигнатура
- GIVEN одинаковое имя с parameter_type_names=null и ().
- WHEN создаются ссылки одного callsite.
- THEN различие сохраняется и не меняет identity callsite.

### Requirement: Локальная идентичность
#### Scenario: Несколько источников одной зависимости
- GIVEN одинаковый selector в разных callsites и repositories.
- WHEN строятся ID.
- THEN ID различаются; изменение version_hint не меняет identity исходного callsite.

### Requirement: Строгий контракт
#### Scenario: Недопустимые поля
- GIVEN RESOLVED/PARTIAL status, target/candidates, blank reason/hints, пустое evidence, недопустимый source type или неизвестный selector kind.
- WHEN документ валидируется.
- THEN он отклоняется.

#### Scenario: Некорректный selector
- GIVEN lowercase HTTP method, relative path, query/fragment в path или blank имена символа, параметра, connection/table.
- WHEN валидируется selector.
- THEN он отклоняется.

#### Scenario: Неподдерживаемый анализ
- GIVEN UNSUPPORTED coverage.
- WHEN certainty отличен от UNKNOWN.
- THEN документ отклоняется.
- WHEN certainty UNKNOWN.
- THEN документ проходит roundtrip.

### Requirement: Источник и evidence локальны
#### Scenario: Ошибка каталога
- GIVEN отсутствующий source, неверный фактический тип, source другого repository или отсутствующий/чужой evidence file.
- WHEN вызывается validate_external_reference.
- THEN проверка завершается ошибкой.

### Requirement: Внешний факт не равен внешней связи
#### Scenario: Локальная связь с ExternalReference
- GIVEN EXTERNAL_DEPENDENCY от локального METHOD к локальному ExternalReference.
- WHEN проверяются endpoints и выполняется roundtrip Relation.
- THEN локальная связь допустима, ExternalReference остаётся UNRESOLVED.
- WHEN kind заменяется CALLS.
- THEN документ отклоняется.

### Requirement: Обратная совместимость
#### Scenario: Аддитивное расширение
- GIVEN прежние документы и расширенный registry.
- WHEN выполняется контрактный набор.
- THEN прежние сценарии проходят, schema актуальна и новые пары EXTERNAL_DEPENDENCY проходят roundtrip.
