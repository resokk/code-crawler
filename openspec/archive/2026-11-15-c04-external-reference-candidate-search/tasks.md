# Tasks: Разрешение кандидатов ExternalReference по запросу

**Priority:** P1  
**Dependencies:** C02,C03

- [x] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [x] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [x] 3. Реализовать: Нормализовать selector-specific lookup (Symbol signature, DB identity, HTTP method/path/service, Kafka/BPMN IDs).
- [x] 4. Реализовать: Фильтровать кандидатов выбранным resolver_context и compatibility constraints, с bounded fanout.
- [x] 5. Реализовать: Возвращать RESOLVED только при единственной доказанной совместимой цели; иначе AMBIGUOUS/PARTIAL/UNRESOLVED с reasons.
- [x] 6. Реализовать: Каждый кандидат связывать с его snapshot, source Evidence, rule и certainty; unknown framework semantics не повышать.
- [x] 7. Добавить сценарий acceptance test: Единственная цель
- [x] 8. Добавить сценарий acceptance test: Два кандидата
- [x] 9. Добавить сценарий acceptance test: Нет кандидата
- [x] 10. Добавить сценарий acceptance test: Превышен fanout
- [x] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [x] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [x] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [x] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [x] 15. По завершении перенести change в archive, не удаляя его спецификации.
