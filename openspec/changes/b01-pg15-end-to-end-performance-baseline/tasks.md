# Tasks: Воспроизводимый baseline производительности PG15

**Priority:** P0  
**Dependencies:** A01 желательно

- [ ] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [ ] 2. Реализовать: Зафиксировать версии PG15, Python, окружение, RAM/CPU, work_mem/shared_buffers, тип workload и commit SHA.
- [ ] 3. Реализовать: Раздельно измерить capture, prepare, analyze, stage, transfer/FK, validation, publication, GC и reader queries.
- [ ] 4. Реализовать: Собрать серии на 400, 1000 файлах и >1 млн UCM entities; failures и OOM документировать как результат, не скрывать.
- [ ] 5. Реализовать: Сохранить RAM RSS, IO, WAL, запросы EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON), stats и воспроизводимый fixture generator.
- [ ] 6. Покрыть автоматическим positive/negative тестом: Замеры привязаны к commit и окружению
- [ ] 7. Покрыть автоматическим positive/negative тестом: Стабильность результатов
- [ ] 8. Покрыть автоматическим positive/negative тестом: Большой масштаб
- [ ] 9. Покрыть автоматическим positive/negative тестом: Безопасность benchmark
- [ ] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [ ] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [ ] 12. Обновить тематические docs/, Coverage и ограничения.
- [ ] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.

## Runner verification (scale evidence pending)

- Current schema includes B04 FK/staging improvements and A06 policy (base `2951af8`).
- Ruff lint/format passed; full mandatory PG15 suite: 1322 passed in 312.07s.
- Final focused B01 suite: 11 passed in 12.45s, including cancellation recovery, ownership cleanup and published-reader preservation.
- Controlled scale series and required remote CI remain pending; do not archive yet.
