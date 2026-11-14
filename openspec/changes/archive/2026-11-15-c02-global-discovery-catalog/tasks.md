# Tasks: Глобальный каталог потенциальных целей

**Priority:** P1  
**Dependencies:** C01, C03 желательно

- [x] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [x] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [x] 3. Реализовать: Разработать search_discovery_entries с repository_id/snapshot_id, entity_id, kind, qualifier, normalized lookup keys и generation.
- [x] 4. Реализовать: Проецировать только факты PUBLISHED и сохранять уникальность ключей без требования единственного глобального кандидата.
- [x] 5. Реализовать: Индексировать symbol FQN+signature, DB identifiers, HTTP route/service, worker/process, reference dataset и Kafka topic; неизвестные типы не выдумывать.
- [x] 6. Реализовать: Поддержать retire/GC/rollback/generation invalidation без переиндексации несвязанных репозиториев.
- [x] 7. Добавить сценарий acceptance test: Каталог неоднозначностей
- [x] 8. Добавить сценарий acceptance test: Published only
- [x] 9. Добавить сценарий acceptance test: Точность ключей
- [x] 10. Добавить сценарий acceptance test: Отмена публикации
- [x] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [x] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [x] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [x] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [x] 15. По завершении перенести change в archive, не удаляя его спецификации.
