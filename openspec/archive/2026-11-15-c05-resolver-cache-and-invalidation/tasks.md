# Tasks: Кэш query-time разрешений с инвалидацией

**Priority:** P1  
**Dependencies:** C02,C03,C04

- [x] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [x] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [x] 3. Реализовать: Задать cache key: ExternalReference selector hash, context fingerprint, discovery generation и resolver algorithm version.
- [x] 4. Реализовать: Хранить candidates и resolution с TTL/limits, provenance и однозначными reasons.
- [x] 5. Реализовать: При изменении publication pointers или generation инвалидация должна вытекать из ключей; старые кэши не показывать.
- [x] 6. Реализовать: Добавить bounded cache size, instrumentation hit/miss, race-safe generation reads.
- [x] 7. Добавить сценарий acceptance test: Freshness
- [x] 8. Добавить сценарий acceptance test: Изоляция контекстов
- [x] 9. Добавить сценарий acceptance test: Неавторитетный кэш
- [x] 10. Добавить сценарий acceptance test: Соревнование поколений
- [x] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [x] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [x] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [x] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [x] 15. По завершении перенести change в archive, не удаляя его спецификации.
