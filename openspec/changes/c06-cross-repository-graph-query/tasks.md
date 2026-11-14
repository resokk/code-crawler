# Tasks: Ограниченный графовый обход между репозиториями

**Priority:** P1  
**Dependencies:** C03,C04,C05

- [ ] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [ ] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [ ] 3. Реализовать: Обходить локальные Relations внутри snapshot; только при ExternalReference вызывать query-time resolver.
- [ ] 4. Реализовать: Ввести depth, fanout, max nodes, max hops между repos, timeout/cancellation и total result cap.
- [ ] 5. Реализовать: Проводить авторизацию каждого repository scope до перехода; предотвращать циклы и сохранять порядок пути.
- [ ] 6. Реализовать: Для каждого edge и remote hop возвращать source and target snapshot, Evidence, certainty, resolution, truncation.
- [ ] 7. Добавить сценарий acceptance test: Два репозитория
- [ ] 8. Добавить сценарий acceptance test: Ambiguous hop
- [ ] 9. Добавить сценарий acceptance test: Depth bound
- [ ] 10. Добавить сценарий acceptance test: ACL
- [ ] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [ ] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [ ] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [ ] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [ ] 15. По завершении перенести change в archive, не удаляя его спецификации.
