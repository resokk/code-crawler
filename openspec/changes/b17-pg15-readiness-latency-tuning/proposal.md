# Proposal: Снижение времени полной проверки readiness без роста памяти

**Priority:** P1

## Why
B02 устранил full SQL hydration, но готовность snapshot остаётся существенной частью end-to-end: B01 до последних изменений измерял 43.13с на 400 файлах и 130.87с на 1000. Readiness включает SQL global invariants, temporary parent/link projections, pointer doubling для scope cycles, model hydration по 2000 entities и LRU 20000. Нужны свежие PG15 планы и оптимизация времени при сохранении строгой проверки.

## Intended outcome
Сокращение измеренного времени индексации без изменения канонических UCM-фактов, публикации, покрытия, разрешения и Evidence.

## Scope
- Добавить per-invariant wall/CPU/SQL EXPLAIN BUFFERS для global identity, scope cycle, SQL statement/variant/origin/binding/context, evidence, ORM и model-level checks; разделить server-time и Python hydration.
- Измерить влияние fetch size 2000, LRU 20000, temp table indexes, pointer-doubling update count, работу join nested paths; выбрать точечные изменения на двух разных fixtures.
- Ускорять только SELECT/temporary projections/prefetch, подтверждённые benchmark, без отключения SQL checks, FK, Coverage и reference validator parity.
- Сохранить repeatable-read snapshot scan, lease, cancellation drain и atomic READY receipt; контролировать temp DB bytes и длительность MVCC view.
- Провести negative parity fixtures для corrupted SQL origin, duplicate producer, cyclic scope, ORM/FK, missing source archive, ambiguous resolution и Unicode slicing.

## Non-goals
- Не заменять строгую валидацию подсчётом entities или доверительным быстрым режимом для публикации.
- Не увеличивать бесконтрольно LRU/cache ради времени.
- Не вводить materialized global validation cache, если он не связан с immutable snapshot/version.

## Dependencies
B09 и завершённая B02 bounded-memory-snapshot-validation.

## Affected code
src/code_crawler/publication.py; src/code_crawler/snapshot_validation.py; src/code_crawler/reader.py; src/code_crawler/validation_benchmark.py; docs/snapshot-validation-invariants.md; tests/integration/test_bounded_validation.py

## Acceptance
- Нижний бюджет времени утверждается после свежего baseline B09; улучшение подтверждается повторными runs без нарушений B02 heap/parity acceptance.
