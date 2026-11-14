# Tasks: Нагрузочная проверка 100+ независимых репозиториев

**Priority:** P1  
**Dependencies:** B01,B02,B03,B04

- [ ] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [ ] 2. Реализовать: Создать workload генератор с 100+ repo keys, смешанными языками, конфликтами FQN и DB names.
- [ ] 3. Реализовать: Нагрузить parallel ingest, publication CAS, reader queries и concurrent GC с ограниченными DB connections.
- [ ] 4. Реализовать: Измерить P50/P95 reader latency, throughput indexing, lock waits, memory, WAL/disk и failure recovery.
- [ ] 5. Реализовать: Проверить fairness jobs, tenant/repository isolation и отсутствие межрепозиторных FK.
- [ ] 6. Покрыть автоматическим positive/negative тестом: Независимая публикация
- [ ] 7. Покрыть автоматическим positive/negative тестом: Независимые имена
- [ ] 8. Покрыть автоматическим positive/negative тестом: Чтение при записи
- [ ] 9. Покрыть автоматическим positive/negative тестом: Сбой одного job
- [ ] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [ ] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [ ] 12. Обновить тематические docs/, Coverage и ограничения.
- [ ] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.
