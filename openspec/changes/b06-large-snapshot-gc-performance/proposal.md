# Proposal: Масштабируемая очистка больших snapshots

## Why
GC работает через DELETE множества строк и триггеров; на больших snapshots время и удержание locks неизвестны.

## Target outcome
Масштабируемая очистка больших snapshots: Измерить GC WALL, locks, WAL, dead tuples и bloat на 100k/1M facts. Рассмотреть безопасное batch-deletion в управляемом графе таблиц; защитить CAS от удаления pinned/active references. Добавить lifecycle cleanup для orphan source blobs и derived search generations с учётом retention. Сохранить retry после crash и отчет количеств удалённых сущностей/байт.

## Scope
- Измерить GC WALL, locks, WAL, dead tuples и bloat на 100k/1M facts.
- Рассмотреть безопасное batch-deletion в управляемом графе таблиц; защитить CAS от удаления pinned/active references.
- Добавить lifecycle cleanup для orphan source blobs и derived search generations с учётом retention.
- Сохранить retry после crash и отчет количеств удалённых сущностей/байт.

## Non-goals
Не вводить сотни partitions по репозиториям без benchmark.

## Dependencies
A01,B01

## Affected code
src/code_crawler/jobs.py; src/code_crawler/migrations/; tests/integration/test_ingest_jobs.py; docs/ingest-jobs.md

## Priority
P1
