# Tasks: Локальные embeddings, pgvector и кэш

**Priority:** P1  
**Dependencies:** C01,A06; model selection отдельный design decision

- [ ] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [ ] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [ ] 3. Реализовать: Выбрать модель и размерность по русскому/английскому коду, нагрузке и лимитам pgvector 0.8.0; задокументировать benchmark вариантов.
- [ ] 4. Реализовать: Создать search_embedding_models, search_embeddings, search_embedding_cache, generation/job tracking с model/preprocessing version.
- [ ] 5. Реализовать: Вычислять векторы из redacted indexed documents, переиспользуя cache по content SHA и model key.
- [ ] 6. Реализовать: Добавить HNSW по выбранной размерности, оценить фильтрацию snapshot/repository и fallback для отсутствующих embeddings.
- [ ] 7. Добавить сценарий acceptance test: Determinism
- [ ] 8. Добавить сценарий acceptance test: Model versioning
- [ ] 9. Добавить сценарий acceptance test: Partial generation
- [ ] 10. Добавить сценарий acceptance test: No exfiltration
- [ ] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [ ] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [ ] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [ ] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [ ] 15. По завершении перенести change в archive, не удаляя его спецификации.
