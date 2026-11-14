# Tasks: Сокращение времени транзакции при индексации

**Priority:** P1  
**Dependencies:** B01; учитывать B02/B05

- [ ] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [ ] 2. Реализовать: Разделить immutable source capture/CPU analysis и стадии транзакционной записи; выбрать spool/staging с ограниченной памятью.
- [ ] 3. Реализовать: Обеспечить snapshot input fingerprint и повторную verify перед фиксацией staged данных.
- [ ] 4. Реализовать: Переиспользованные facts клонировать из того же immutable baseline при CAS publication, без long-running repo lock.
- [ ] 5. Реализовать: Обеспечить idempotent cleanup after crash и работу concurrent indexing jobs.
- [ ] 6. Покрыть автоматическим positive/negative тестом: Анализ вне write transaction
- [ ] 7. Покрыть автоматическим positive/negative тестом: Исходники изменились
- [ ] 8. Покрыть автоматическим positive/negative тестом: Конкурентная публикация
- [ ] 9. Покрыть автоматическим positive/negative тестом: Отказ на staging
- [ ] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [ ] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [ ] 12. Обновить тематические docs/, Coverage и ограничения.
- [ ] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.
