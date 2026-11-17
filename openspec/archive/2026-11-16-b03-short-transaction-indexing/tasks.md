# Tasks: Сокращение времени транзакции при индексации

**Priority:** P1  
**Dependencies:** B01; учитывать B02/B05

- [x] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [x] 2. Реализовать: Разделить immutable source capture/CPU analysis и стадии транзакционной записи; выбрать spool/staging с ограниченной памятью.
- [x] 3. Реализовать: Обеспечить snapshot input fingerprint и повторную verify перед фиксацией staged данных.
- [x] 4. Реализовать: Переиспользованные facts клонировать из того же immutable baseline при CAS publication, без long-running repo lock.
- [x] 5. Реализовать: Обеспечить idempotent cleanup after crash и работу concurrent indexing jobs.
- [x] 6. Покрыть автоматическим positive/negative тестом: Анализ вне write transaction
- [x] 7. Покрыть автоматическим positive/negative тестом: Исходники изменились
- [x] 8. Покрыть автоматическим positive/negative тестом: Конкурентная публикация
- [x] 9. Покрыть автоматическим positive/negative тестом: Отказ на staging
- [x] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [x] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [x] 12. Обновить тематические docs/, Coverage и ограничения.
- [x] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.
