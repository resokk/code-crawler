# Tasks: Воспроизводимый baseline производительности PG15

**Priority:** P0  
**Dependencies:** A01 желательно

- [x] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [x] 2. Реализовать: Зафиксировать версии PG15, Python, окружение, RAM/CPU, work_mem/shared_buffers, тип workload и commit SHA.
- [x] 3. Реализовать: Раздельно измерить capture, prepare, analyze, stage, transfer/FK, validation, publication, GC и reader queries.
- [x] 4. Реализовать: Собрать серии на 400, 1000 файлах и >1 млн UCM entities; failures и OOM документировать как результат, не скрывать.
- [x] 5. Реализовать: Сохранить RAM RSS, IO, WAL, запросы EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON), stats и воспроизводимый fixture generator.
- [x] 6. Покрыть автоматическим positive/negative тестом: Замеры привязаны к commit и окружению
- [x] 7. Покрыть автоматическим positive/negative тестом: Стабильность результатов
- [x] 8. Покрыть автоматическим positive/negative тестом: Большой масштаб
- [x] 9. Покрыть автоматическим positive/negative тестом: Безопасность benchmark
- [x] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [x] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [x] 12. Обновить тематические docs/, Coverage и ограничения.
- [x] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.

## Runner verification (scale evidence pending)

- Current schema includes B04 FK/staging improvements and A06 policy (base `2951af8`).
- Ruff lint/format passed; full mandatory PG15 suite: 1322 passed in 312.07s.
- Final focused B01 suite: 11 passed in 12.45s, including cancellation recovery, ownership cleanup and published-reader preservation.
- Controlled scale series and required remote CI remain pending; do not archive yet.

## Controlled series and final local verification

- Measured clean implementation: `6eaa9841d9a1b4352ac8714c758d3b684afb8bf3`.
- 400 files × 3: 140,717 entities each; index 92.283/92.576/93.094 s;
  validation 40.792/43.132/51.347 s. GC exceeded 120 s each time;
  published pointer and reader results remained unchanged after cancellation.
- 1,000 files: 352,817 entities, validation/publication/readers completed;
  disk-reserve supervisor stopped clone at 528,424,960 free bytes.
- 3,002-file >1M-target attempt: stopped on transfer at 531,554,304 free bytes;
  no completed >1M snapshot is claimed. Failure is an accepted explicit outcome
  of the scale scenario, not a production scalability ceiling.
- Full raw JSON retained as gzip, integrity hashes and compact complete-stage
  distributions recorded under docs/benchmarks/end-to-end-pg15-2026-11-16*.
  Format-v2 aggregation excludes incomplete slice totals; original raw-v1 report
  is unchanged. No benchmark-owned DBs remained after the series.
- Final local full PG15 suite: **1325 passed in 314.76s**; focused suite:
  **14 passed in 13.57s**. Ruff lint/format passed (395 files).
- Required remote CI for final evidence implementation `3de9d3d01f2fb65a75bb24d791af4cfc4cbff146`: success, **1325 passed in 291.55s**, clean migrations and working-tree checks passed: https://github.com/resokk/code-crawler/actions/runs/43927411180.
- Initial runner CI also passed: https://github.com/resokk/code-crawler/actions/runs/43921168361 (1322 tests). All acceptance scenarios are satisfied, including the explicitly permitted documented large-scale failure outcome.
