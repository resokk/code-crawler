# Tasks: Масштабируемая очистка больших snapshots

**Priority:** P1  
**Dependencies:** A01,B01

- [ ] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [ ] 2. Реализовать: Измерить GC WALL, locks, WAL, dead tuples и bloat на 100k/1M facts.
- [ ] 3. Реализовать: Рассмотреть безопасное batch-deletion в управляемом графе таблиц; защитить CAS от удаления pinned/active references.
- [ ] 4. Реализовать: Добавить lifecycle cleanup для orphan source blobs и derived search generations с учётом retention.
- [ ] 5. Реализовать: Сохранить retry после crash и отчет количеств удалённых сущностей/байт.
- [ ] 6. Покрыть автоматическим positive/negative тестом: Нельзя удалять pinned
- [ ] 7. Покрыть автоматическим positive/negative тестом: Нет побочных удалений
- [ ] 8. Покрыть автоматическим positive/negative тестом: Устойчивость отказа
- [ ] 9. Покрыть автоматическим positive/negative тестом: Измеренная стоимость
- [ ] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [ ] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [ ] 12. Обновить тематические docs/, Coverage и ограничения.
- [ ] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.
