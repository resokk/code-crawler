# UCM incremental indexing

## Проблема и цель

Повторная загрузка UCM пока требует нового разбора всех исходников. Нужны fingerprint inventory, file ownership и dependency invalidation, чтобы анализировать только изменённые и зависимые файлы, сохраняя immutable history.

## Границы

Git/worktree capture, план изменений, FileAnalysis callback, reuse facts из опубликованного baseline, новый полный batch и транзакционная загрузка manifests. Migration 0006, OpenSpec и tests. Legacy CLI не переключается: миграция writer/reader остаётся change 13. Language adapters, server-side fact cloning и streaming не входят в эту задачу.
