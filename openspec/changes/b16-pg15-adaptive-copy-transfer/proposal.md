# Proposal: Сокращение количества PostgreSQL COPY/INSERT/TRUNCATE и round-trip

**Priority:** P1

## Why
_stage и _transfer вызываются на каждую file slice с отдельными COPY для каждого типа фактов, INSERT SELECT и TRUNCATE per table. На 400 файлах baseline показывает 15.76 с transfer, 10.76 с FK; высокая частота маленьких операций может отнимать заметное время на PostgreSQL протокол/DDL/locks.

## Intended outcome
Сокращение измеренного времени индексации без изменения канонических UCM-фактов, публикации, покрытия, разрешения и Evidence.

## Scope
- Собрать count/latency/row-size для каждого COPY, INSERT SELECT, TRUNCATE, ANALYZE и deferred FK flush; выделить число маленьких таблиц и запросов per slice.
- Ввести bounded target row/byte budget для объединения слишком маленьких staged transfers и явно ограничивать maximum batch для очень больших полей; сохранить текущий алгоритм как baseline.
- Переиспользовать temp staging tables и column order/transfer plans, не отключая все FK и не меняя canonical immutable tables.
- Применять более редкие ANALYZE только там, где это подтверждено статистикой/plans PG15; после массовой загрузки сохранить корректную deferred verification до commit.
- На PostgreSQL 15 сравнить 400/1000-file, high-table-count и SQL-dense fixtures, сохранив rollback при duplicate/ref error, отсутствие orphan staging и прежний publication pointer.

## Non-goals
- Не отключать constraints/triggers, не использовать unlogged canonical data, не менять applied migrations ради скорости.
- Не смешивать snapshot_id разных репозиториев в один staging buffer.
- Не считать ускорение прогрева PostgreSQL доказательством улучшения при холодном кэше.

## Dependencies
B09, B04 already done, B05 будущая bounded streaming.

## Affected code
src/code_crawler/ingestion.py; src/code_crawler/incremental.py; src/code_crawler/bulk_benchmark.py; src/code_crawler/migrations/ (только новые при необходимости); tests/integration/test_bulk_ingestion.py; docs/ucm-ingestion.md

## Acceptance
- Измеренное улучшение total COPY+transfer на targeted fixture без роста deferred-FK/disk costs, с отдельным report per-table. Если нет выигрыша — сохранить нынешний путь.
