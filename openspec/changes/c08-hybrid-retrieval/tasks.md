# Tasks: Гибридный exact/FTS/vector/graph поиск

**Priority:** P1  
**Dependencies:** C01,C06,C07

- [ ] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [ ] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [ ] 3. Реализовать: Реализовать независимые exact, FTS/trigram, vector candidate producers с общим фильтром repo/snapshot/ACL.
- [ ] 4. Реализовать: Комбинировать результаты через настраиваемую RRF или понятный ranking с traceable component scores.
- [ ] 5. Реализовать: Обогащать top candidates только bounded graph expansion с Evidence, certainty и coverage.
- [ ] 6. Реализовать: Измерять retrieval quality на русском/английском наборе вопросов по schema+SQL+API, фиксировать метрики без выдуманных процентов.
- [ ] 7. Добавить сценарий acceptance test: Exact priority
- [ ] 8. Добавить сценарий acceptance test: Semantic non-proof
- [ ] 9. Добавить сценарий acceptance test: Snapshot scope
- [ ] 10. Добавить сценарий acceptance test: Explainable ranking
- [ ] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [ ] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [ ] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [ ] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [ ] 15. По завершении перенести change в archive, не удаляя его спецификации.
