# Proposal: Безопасная очистка UCM snapshots

## Why
jobs._delete_snapshots() обнаруживает все таблицы public с колонкой snapshot_id и удаляет из них строки; посторонняя таблица может попасть в GC.

## Goal
Удалять только подконтрольные UCM таблицы конкретных snapshots в проверяемом FK-safe порядке; исключить неконтролируемое расширение области DELETE.

## Scope
- Определить явный allowlist таблиц из управляемой схемы UCM/ingest/search/resolver; поддерживать его при каждой миграции.
- В startup/GC preflight сравнивать allowlist с актуальными FK и snapshot-bearing таблицами; незнакомая таблица не должна удаляться по умолчанию.
- Проверять state и publication pointer под блокировкой; закреплённые/используемые snapshots оставлять нетронутыми.
- Обрабатывать связные таблицы с контролируемым порядком/DEFERRED constraints, возвращать отчёт количества удалённых строк и ошибок.

## Non-goals
Не вводить автоматические периодические задания и не переходить к PG partitioning.

## Dependencies
нет

## Impacted code
src/code_crawler/jobs.py; src/code_crawler/migrations/; tests/integration/test_ingest_jobs.py; docs/ingest-jobs.md

## Priority
P0

## Acceptance summary
1. Только управляемые таблицы.
2. Сохранность опубликованных данных.
3. Атомарность удаления.
4. Прозрачность.
