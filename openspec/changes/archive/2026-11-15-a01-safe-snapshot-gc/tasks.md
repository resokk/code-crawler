# Tasks: Безопасная очистка UCM snapshots

Завершено 2026-11-15. Приоритет P0; зависимости отсутствуют. Критерии приёмки подтверждены до архивирования.

- [x] 1. Оценить существующий код и зафиксировать regression fixture, воспроизводящий указанную проблему.
- [x] 2. Утвердить минимальные новые типы/аргументы и обратную совместимость с публичными UCM/CLI/MCP контрактами.
- [x] 3. Определить явный allowlist таблиц из управляемой схемы UCM/ingest/search/resolver; поддерживать его при каждой миграции. — реализовать только в рамках этого change.
- [x] 4. В startup/GC preflight сравнивать allowlist с актуальными FK и snapshot-bearing таблицами; незнакомая таблица не должна удаляться по умолчанию. — реализовать только в рамках этого change.
- [x] 5. Проверять state и publication pointer под блокировкой; закреплённые/используемые snapshots оставлять нетронутыми. — реализовать только в рамках этого change.
- [x] 6. Обрабатывать связные таблицы с контролируемым порядком/DEFERRED constraints, возвращать отчёт количества удалённых строк и ошибок. — реализовать только в рамках этого change.
- [x] 7. Добавить тест: Негативный интеграционный тест: произвольная public.custom_table(snapshot_id) не удаляется.
- [x] 8. Добавить тест: Интеграция: RETIRED удаляется; PUBLISHED/READY/VALIDATING сохраняются.
- [x] 9. Добавить тест: Инъекция ошибки FK посередине GC и проверка rollback.
- [x] 10. Добавить тест: Проверка известного и неизвестного migration state.
- [x] 11. Проверить негативные сценарии спецификации: никакой ложной resolved-связи, повреждения snapshot или раскрытия данных.
- [x] 12. При изменении БД добавить новую миграцию и PG15 integration test; не редактировать применённые миграции.
- [x] 13. Обновить соответствующие docs/ и указать ограничения Coverage, а не скрывать их.
- [x] 14. Запустить `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` и обязательный PG15 CI при затрагивании хранилища.
- [x] 15. Подтвердить критерии приёмки; только затем отмечать чекбоксы и архивировать OpenSpec.

## Подтверждение приёмки

- Реализация: `c65094e` (базовый allowlist и foreign-table regression — `cefc213`).
- PostgreSQL 15: 866 passed, 0 skipped/failures/errors; обязательный прогон с
  `--require-postgres --strict-markers`. Ruff check/format и actionlint прошли.
- Hosted [CI / PostgreSQL 15](https://github.com/resokk/code-crawler/actions/runs/43646593756)
  для `c65094eeb370752b15ac30102b597ddcba842405` завершён успешно.
- Пункты 7–11: foreign UUID/text tables, protected states, FK/cascade/inheritance
  preflight, migration drift/concurrency, busy rows, live jobs (включая своё
  соединение), reader/search leases, partial-delete failure, retry/cancellation
  и отсутствие source bytes в error report покрыты интеграционными тестами.
- Пункт 12: DDL не менялся; новая миграция не нужна. Используются существующие
  constraints/guards и PostgreSQL advisory locks.
- Пункт 13: GC не создаёт analysis facts или Coverage; ограничения участия читателей,
  известной схемы и unsupported inheritance/partitioning явно описаны в docs/.
- Каноническая спецификация перенесена в `openspec/specs/safe-snapshot-gc/spec.md`;
  change сохранён в архиве после прохождения проверок.
