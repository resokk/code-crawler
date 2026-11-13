# UCM relations

## ADDED Requirements

### Requirement: Типизированный immutable registry
Relation SHALL соответствовать паре EntityType из RelationKind registry.

#### Scenario: Допустимые пары
- GIVEN каждая зарегистрированная пара source/target.
- WHEN Relation проходит JSON roundtrip.
- THEN типы и поля сохраняются.

#### Scenario: Недопустимые пары и кандидаты
- GIVEN запрещённый source, target или PARTIAL candidate.
- WHEN Relation валидируется.
- THEN документ отклоняется.

#### Scenario: Полнота реестра
- GIVEN RelationKind enum.
- WHEN читается relation_registry().
- THEN все kinds присутствуют, изменение mapping запрещено.

### Requirement: Честные статусы разрешения
#### Scenario: Неразрешённые результаты
- GIVEN UNRESOLVED без кандидатов, PARTIAL с одним или AMBIGUOUS с двумя уникальными кандидатами и reason.
- WHEN сериализуется relation с UNKNOWN certainty.
- THEN candidates сохраняются, подтверждённый target отсутствует.
- WHEN certainty меняется на STATIC_PROVEN.
- THEN документ отклоняется.

#### Scenario: Противоречивое разрешение
- GIVEN отсутствующий target у RESOLVED, target/candidates в недопустимом статусе, отсутствующий/blank reason, мало или повторные candidates.
- WHEN Resolution валидируется.
- THEN документ отклоняется.

### Requirement: Coverage не подменяет доказательство
#### Scenario: Причины неполноты
- GIVEN COMPLETE с reasons либо PARTIAL/UNSUPPORTED без непустых reasons.
- WHEN Coverage валидируется.
- THEN документ отклоняется.

#### Scenario: Неподдерживаемая capability
- GIVEN UNSUPPORTED coverage.
- WHEN relation UNKNOWN/UNRESOLVED проходит roundtrip.
- THEN ограничение сохранено.
- WHEN relation утверждает RESOLVED или INFERRED.
- THEN документ отклоняется.

#### Scenario: Вывод по разрешённой цели
- GIVEN RESOLVED с INFERRED certainty.
- WHEN строится Relation.
- THEN certainty остаётся INFERRED.

### Requirement: Evidence обязателен
#### Scenario: Нет обоснования
- GIVEN пустой evidence tuple, blank rule или отсутствие source_range.
- WHEN валидируется документ.
- THEN он отклоняется.

### Requirement: Проверка реальных локальных концов
#### Scenario: Обычный и рекурсивный вызов
- GIVEN каталог с реальными METHOD и SourceFile.
- WHEN validate_relation_endpoints проверяет CALLS, включая вызов себя.
- THEN проверка успешна.

#### Scenario: Отсутствие, тип и repository
- GIVEN отсутствующий source/target/candidate, неверный фактический тип, endpoint другого repository или отсутствующий/чужой evidence file.
- WHEN проверяются endpoints.
- THEN проверка завершается ошибкой.

#### Scenario: Подтипы сущностей
- GIVEN CALLS от FIELD Symbol либо RETURN Operation, или DECLARES от REFERENCE Occurrence.
- WHEN проверяются endpoints.
- THEN связь отклоняется.
- WHEN occurrence заменяется DECLARATION.
- THEN DECLARES принимается.

### Requirement: Аддитивный экспорт
#### Scenario: Старые документы и новая Relation
- GIVEN расширенные EntityType и EntityDocument.
- WHEN выполняется весь контрактный набор.
- THEN прежние документы читаются, экспорт JSON Schema актуален и содержит все entity types.
