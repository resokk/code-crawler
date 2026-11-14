# Tasks: Ускорение загрузки через FK и индексы

**Priority:** P1  
**Dependencies:** B01; совместим с B03

- [ ] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [ ] 2. Реализовать: Измерить COPY staging, INSERT SELECT и SET CONSTRAINTS IMMEDIATE отдельно на PG15.
- [ ] 3. Реализовать: Изучить collations C/locale для entity IDs и эффект индексов; менять схему только новой forward migration.
- [ ] 4. Реализовать: Оптимизировать перенесение в canonical таблицы, порядок FK, access patterns и ограничить temp space.
- [ ] 5. Реализовать: Сравнить целостность и результаты до/после, rollback при нарушении FK и overhead добавленных индексов.
- [ ] 6. Покрыть автоматическим positive/negative тестом: Корректность FK
- [ ] 7. Покрыть автоматическим positive/negative тестом: Контролируемая скорость
- [ ] 8. Покрыть автоматическим positive/negative тестом: Независимость collation
- [ ] 9. Покрыть автоматическим positive/negative тестом: Возврат к прошлой версии
- [ ] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [ ] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [ ] 12. Обновить тематические docs/, Coverage и ограничения.
- [ ] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.
