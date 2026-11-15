# Tasks: Ограниченный графовый обход между репозиториями

**Priority:** P1  
**Dependencies:** C03,C04,C05

- [x] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [x] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [x] 3. Реализовать: Обходить локальные Relations внутри snapshot; только при ExternalReference вызывать query-time resolver.
- [x] 4. Реализовать: Ввести depth, fanout, max nodes, max hops между repos, timeout/cancellation и total result cap.
- [x] 5. Реализовать: Проводить авторизацию каждого repository scope до перехода; предотвращать циклы и сохранять порядок пути.
- [x] 6. Реализовать: Для каждого edge и remote hop возвращать source and target snapshot, Evidence, certainty, resolution, truncation.
- [x] 7. Добавить сценарий acceptance test: Два репозитория
- [x] 8. Добавить сценарий acceptance test: Ambiguous hop
- [x] 9. Добавить сценарий acceptance test: Depth bound
- [x] 10. Добавить сценарий acceptance test: ACL
- [x] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [x] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [x] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [x] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [x] 15. По завершении перенести change в archive, не удаляя его спецификации.

Storage unchanged: task 12 requires no migration. Acceptance fixtures and expected
paths are documented in `docs/cross-repository-graph.md`; tests cover both local
and cross-repository cycles, ambiguity, bounds, ACL, version changes and rollback.
