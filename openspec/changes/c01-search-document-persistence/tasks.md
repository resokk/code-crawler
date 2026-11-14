# Tasks: Хранение версионированных поисковых документов

**Priority:** P1  
**Dependencies:** A06 желательно; B02

- [ ] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [ ] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [ ] 3. Реализовать: Создать search_documents и search_index_generations с (repository,snapshot,generation,entity_id,document_type,content,hash,provenance).
- [ ] 4. Реализовать: Обеспечить deterministic projection: одинаковые UCM facts + версия генератора дают одинаковые hashes и doc identity.
- [ ] 5. Реализовать: Публиковать generation атомарно и не показывать incomplete batches; поддержать reindex search без изменения UCM snapshot.
- [ ] 6. Реализовать: Разделить target-language/summary и redacted source; учитывать secret policy и ACL по repository.
- [ ] 7. Добавить сценарий acceptance test: Повторная проекция
- [ ] 8. Добавить сценарий acceptance test: Атомарная видимость
- [ ] 9. Добавить сценарий acceptance test: Provenance
- [ ] 10. Добавить сценарий acceptance test: Scope
- [ ] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [ ] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [ ] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [ ] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [ ] 15. По завершении перенести change в archive, не удаляя его спецификации.
