# Tasks: Хранение версионированных поисковых документов

**Priority:** P1  
**Dependencies:** A06 желательно; B02

- [x] 1. Воспроизвести исходное ограничение/сценарий на фиксированном fixture и описать expected output.
- [x] 2. Описать точный контракт полей/API, правила versioning и backwards compatibility.
- [x] 3. Реализовать: Создать search_documents и search_index_generations с (repository,snapshot,generation,entity_id,document_type,content,hash,provenance).
- [x] 4. Реализовать: Обеспечить deterministic projection: одинаковые UCM facts + версия генератора дают одинаковые hashes и doc identity.
- [x] 5. Реализовать: Публиковать generation атомарно и не показывать incomplete batches; поддержать reindex search без изменения UCM snapshot.
- [x] 6. Реализовать: Разделить target-language/summary и redacted source; учитывать secret policy и ACL по repository.
- [x] 7. Добавить сценарий acceptance test: Повторная проекция
- [x] 8. Добавить сценарий acceptance test: Атомарная видимость
- [x] 9. Добавить сценарий acceptance test: Provenance
- [x] 10. Добавить сценарий acceptance test: Scope
- [x] 11. Добавить negative tests: разные snapshots/repos, ambiguity, partial resolution, denied access и rollback.
- [x] 12. Если меняется storage — отдельная migration + PostgreSQL 15 integration tests; никакой DDL вне миграций.
- [x] 13. Обновить docs и Coverage/Resolution/Evidence, проверить отсутствие ложных DEFINITE/STATIC_PROVEN связей.
- [x] 14. Запустить ruff, pytest/PG15 CI; зафиксировать coverage и benchmark при необходимости.
- [x] 15. По завершении перенести change в archive, не удаляя его спецификации.


## Verification evidence

Local PostgreSQL 15 (Docker postgres:15), 2026-11-15:
`uv run ruff check .`, `uv run ruff format --check .`,
`uv run pytest --require-postgres -x -q`: **890 passed in 134.69s**.

Acceptance coverage: tests/test_search_storage.py and
tests/integration/test_search_document_storage.py. Covers deterministic rebuild,
ORM/SQL/symbol provenance, AMBIGUOUS/UNRESOLVED/PARTIAL preservation, policy
redaction/failure, cross-repository/snapshot rejection, denied access, incomplete
seal rejection, SQL failure/cancellation rollback, concurrent CAS, pinned
pagination, empty generation, full/incremental reuse and retired snapshot GC.
Existing query benchmark regression also passes on historical migration prefixes.
No performance claim or new benchmark is made; B02 remains open. A02/A06 plug in
through mandatory trusted authorization scope and explicit versioned redactor.

After rebasing onto upstream Kotlin/JavaScript adapters, the complete local suite
passed **927 tests in 135.01s**. Implementation commit: 712018b668f4c86e68e2712a43eebf764fedf06c.
GitHub CI / PostgreSQL 15 succeeded:
https://github.com/resokk/code-crawler/actions/runs/43649003961
All migrations, lint, formatting, tests and clean-working-tree checks passed.
Archived on 2026-11-15 (Europe/Moscow); see completion.md.
