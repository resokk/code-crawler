# Tasks: Точный поиск SQL-доступов в контексте физической БД

Приоритет P1; зависит: Существующие database identity и structural search.

- [x] 1. Оценить существующий код и зафиксировать regression fixture, воспроизводящий указанную проблему.
- [x] 2. Утвердить минимальные новые типы/аргументы и обратную совместимость с публичными UCM/CLI/MCP контрактами.
- [x] 3. Существующий API поиска по table/column оставить как синтаксический с явным mode в ответе. — реализовать только в рамках этого change.
- [x] 4. Добавить параметры database_key, schema_version_key и database_object_id, валидировать совместимую комбинацию. — реализовать только в рамках этого change.
- [x] 5. Точный режим строить по RESOLVES_DATABASE_OBJECT/DatabaseAccess с проверкой контекста snapshot и schema version. — реализовать только в рамках этого change.
- [x] 6. Не включать UNRESOLVED или AMBIGUOUS в группу точных физических совпадений; вернуть их отдельно либо явно отразить coverage. — реализовать только в рамках этого change.
- [x] 7. Индексировать часто используемые фильтры после EXPLAIN на PG15. — реализовать только в рамках этого change.
- [x] 8. Добавить тест: Тест с двумя DB contexts и одинаковой table name.
- [x] 9. Добавить тест: Тест quoted vs unquoted identifiers.
- [x] 10. Добавить тест: Тест unresolved access и отсутствия ложного exact match.
- [x] 11. Добавить тест: Проверка snapshot isolation и плана PG15.
- [x] 12. Проверить негативные сценарии спецификации: никакой ложной resolved-связи, повреждения snapshot или раскрытия данных.
- [x] 13. При изменении БД добавить новую миграцию и PG15 integration test; не редактировать применённые миграции.
- [x] 14. Обновить соответствующие docs/ и указать ограничения Coverage, а не скрывать их.
- [ ] 15. Запустить `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` и обязательный PG15 CI при затрагивании хранилища.
- [ ] 16. Подтвердить критерии приёмки; только затем отмечать чекбоксы и архивировать OpenSpec.

## Verification evidence

- Local full mandatory PostgreSQL 15 suite: **1284 passed in 280.10s**.
- Ruff lint and formatting: passed (380 files).
- Combined A03/A04 focused regressions: 33 passed; strengthened execution/context proof regression: 1 passed.
- Migration 0030 preserves results; captured PG15 plans and workload are in `docs/benchmarks/database-qualified-search-pg15.json`.
- Mandatory remote PG15 CI and final acceptance remain pending before archive.
