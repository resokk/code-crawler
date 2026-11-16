# Tasks: Разграничение обнаружения SQL и доказанного execution в поиске

Приоритет P1; A03 остаётся отдельным change: квалификаторы поиска здесь не меняются.

- [x] 1. Оценить существующий код и зафиксировать regression fixture, воспроизводящий указанную проблему.
- [x] 2. Утвердить минимальные новые типы/аргументы и обратную совместимость с публичными UCM/CLI/MCP контрактами.
- [x] 3. Определить typed output contract: discovery_status, execution_link_status, target_resolution, evidence/certainty отдельно. — реализовать только в рамках этого change.
- [x] 4. Для бездоказательного SQL сохранить found statement, но выставлять execution_link_status=NOT_ESTABLISHED. — реализовать только в рамках этого change.
- [x] 5. Для execution sink без восстановленного SQL предоставить execution record с пустым statements и явным coverage. — реализовать только в рамках этого change.
- [x] 6. Не менять семантику сохранённых UCM relations и не повышать certainty из-за текстового совпадения. — реализовать только в рамках этого change.
- [x] 7. Обновить docstrings MCP и примеры безопасных ответов агентам. — реализовать только в рамках этого change.
- [x] 8. Добавить тест: Fixture: SQL literal never executed.
- [x] 9. Добавить тест: Fixture: constructed SQL executed via preparedStatement.
- [x] 10. Добавить тест: Fixture: sink with unknown text.
- [x] 11. Добавить тест: Проверка обратной совместимости и структуры MCP DTO.
- [x] 12. Проверить негативные сценарии спецификации: никакой ложной resolved-связи, повреждения snapshot или раскрытия данных.
- [x] 13. При изменении БД добавить новую миграцию и PG15 integration test; не редактировать применённые миграции.
- [x] 14. Обновить соответствующие docs/ и указать ограничения Coverage, а не скрывать их.
- [x] 15. Запустить `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` и обязательный PG15 CI при затрагивании хранилища.
- [x] 16. Подтвердить критерии приёмки; только затем отмечать чекбоксы и архивировать OpenSpec.

## Реализация и проверки

- Дополняющий TypedDict `SqlSearchStatus`; прежние аргументы и поля сохранены.
- EXECUTES_SQL, EXECUTES_STATEMENT и statement→access возвращаются с исходными
  Evidence/Coverage/certainty; INFERRED не повышается до STATIC_PROVEN.
- SQL без sink: FOUND / NOT_ESTABLISHED; DB target_resolution копирует сохранённый
  статус access. Sink без statement: пустой список и PARTIAL с явной причиной.
- Regression fixture: неисполняемый DELETE, SQL-конкатенация + prepareStatement,
  динамический неизвестный SQL; проверены MCP DTO и неизменность числа UCM relations.
- Миграция не требуется: изменения только в read-only проекциях и документации.
- Целевые PG15 tests: 5 passed; lint и format check прошли.
- Полный локальный PG15 прогон: 1261 passed (462.37s). После последних уточнений проекции целевые tests также прошли: 5 passed.
- Обязательный PostgreSQL 15 CI: 1261 passed (284.13s), success.
  https://github.com/resokk/code-crawler/actions/runs/43859377294
- Критерии приёмки подтверждены; спецификация сохранена в архиве вместе с completion receipt.
