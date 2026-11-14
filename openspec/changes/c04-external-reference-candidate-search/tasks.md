# Tasks: Разрешение кандидатов ExternalReference по запросу

**Priority:** P1  
**Dependencies:** C02,C03

- [ ] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [ ] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [ ] 3. Реализовать: Нормализовать selector-specific lookup (Symbol signature, DB identity, HTTP method/path/service, Kafka/BPMN IDs).
- [ ] 4. Реализовать: Фильтровать кандидатов выбранным resolver_context и compatibility constraints, с bounded fanout.
- [ ] 5. Реализовать: Возвращать RESOLVED только при единственной доказанной совместимой цели; иначе AMBIGUOUS/PARTIAL/UNRESOLVED с reasons.
- [ ] 6. Реализовать: Каждый кандидат связывать с его snapshot, source Evidence, rule и certainty; unknown framework semantics не повышать.
- [ ] 7. Добавить сценарий acceptance test: Единственная цель
- [ ] 8. Добавить сценарий acceptance test: Два кандидата
- [ ] 9. Добавить сценарий acceptance test: Нет кандидата
- [ ] 10. Добавить сценарий acceptance test: Превышен fanout
- [ ] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [ ] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [ ] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [ ] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [ ] 15. По завершении перенести change в archive, не удаляя его спецификации.
