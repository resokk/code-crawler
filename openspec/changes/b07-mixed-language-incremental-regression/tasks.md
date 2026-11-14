# Tasks: Инкрементальность на реальных Java/Groovy/PLPlus репозиториях

**Priority:** P1  
**Dependencies:** B05 желательно

- [ ] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [ ] 2. Реализовать: Подготовить версионированный test fixture, представляющий package imports, CFT selectors и Groovy dependencies.
- [ ] 3. Реализовать: Фиксировать список adapter invocations и reuse manifests при изменении Java source/catalog.
- [ ] 4. Реализовать: Проверить транзитивную invalidation связанных языков и отсутствие сброса unrelated facts.
- [ ] 5. Реализовать: Проверить rename/delete, отсутствующие dependencies и untracked files.
- [ ] 6. Покрыть автоматическим positive/negative тестом: Независимый адаптер
- [ ] 7. Покрыть автоматическим positive/negative тестом: Транзитивность
- [ ] 8. Покрыть автоматическим positive/negative тестом: Обработка удаления
- [ ] 9. Покрыть автоматическим positive/negative тестом: Сравнение полного и инкрементального
- [ ] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [ ] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [ ] 12. Обновить тематические docs/, Coverage и ограничения.
- [ ] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.
