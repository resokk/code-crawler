# Tasks: Сквозная bounded-memory индексация

**Priority:** P1  
**Dependencies:** B02,B03,B04

- [ ] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [ ] 2. Реализовать: Ввести ограниченный in-flight budget по количеству entities/bytes, а не только файлов; считать max size per file.
- [ ] 3. Реализовать: Использовать stream API с staged writes и server-side clone unchanged facts без объединения в полный UcmBatch.
- [ ] 4. Реализовать: Гарантировать cross-file references, forward references, deterministic ownership/dependency manifest и source archive consistency.
- [ ] 5. Реализовать: Добавить отмену, повтор и fault injection; memory measurement на incremental/full режимах.
- [ ] 6. Покрыть автоматическим positive/negative тестом: Память не пропорциональна размеру snapshot
- [ ] 7. Покрыть автоматическим positive/negative тестом: Данные без изменений
- [ ] 8. Покрыть автоматическим positive/negative тестом: Forward references
- [ ] 9. Покрыть автоматическим positive/negative тестом: Сбой не публикует
- [ ] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [ ] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [ ] 12. Обновить тематические docs/, Coverage и ограничения.
- [ ] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.
