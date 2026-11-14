# Tasks: Порционная проверка целостности snapshot

**Priority:** P0  
**Dependencies:** B01; разделить на inventory, references и readiness

- [ ] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [ ] 2. Реализовать: Сформировать полный реестр UcmBatch semantic invariants с отображением на проверки SQL/stream.
- [ ] 3. Реализовать: Проверять unique identities, entity types, typed FK, evidence ranges, relation endpoints, scopes, SQL construction/bindings и ORM инварианты порциями.
- [ ] 4. Реализовать: Сохранять validation receipt и READY только по завершении всех проверок в контролируемом транзакционном протоколе.
- [ ] 5. Реализовать: Сопоставить решения старого и нового валидатора на корректных и искусственно повреждённых snapshots; убрать обязательную полную model hydration из readiness.
- [ ] 6. Покрыть автоматическим positive/negative тестом: Эквивалентность валидации
- [ ] 7. Покрыть автоматическим positive/negative тестом: Ограниченное потребление памяти
- [ ] 8. Покрыть автоматическим positive/negative тестом: Безопасная публикация
- [ ] 9. Покрыть автоматическим positive/negative тестом: Конкурентность
- [ ] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [ ] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [ ] 12. Обновить тематические docs/, Coverage и ограничения.
- [ ] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.
