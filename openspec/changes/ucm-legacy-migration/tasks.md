# Tasks

- [x] До реализации описать compatibility migration и её семантические границы в docs/ucm-legacy-migration.md.
- [x] Добавить migration 0007: stable mapping, read backend и immutable graph projection.
- [x] Переиспользовать Java/PLPlus analyzers для captured bytes без изменения parser semantics.
- [x] Добавить envelope converter и сохранить полный legacy ответ отдельно от canonical facts.
- [x] Добавить checked migration, comparison, persistent read switch и stateless read API.
- [x] Подключить migrate-index/compare-index/use-index/show-index к CLI.
- [x] Проверить 5 PostgreSQL scenarios, включая отдельные CLI processes и shared PLPlus data/calls.
- [x] Обновить общую документацию: полный suite PostgreSQL 15 — 348 passed; Ruff, format и diff checks без ошибок.
