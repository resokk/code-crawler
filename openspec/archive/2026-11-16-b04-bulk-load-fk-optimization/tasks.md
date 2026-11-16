# Tasks: Ускорение загрузки через FK и индексы

**Priority:** P1  
**Dependencies:** B01; совместим с B03

- [x] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [x] 2. Реализовать: Измерить COPY staging, INSERT SELECT и SET CONSTRAINTS IMMEDIATE отдельно на PG15.
- [x] 3. Реализовать: Изучить collations C/locale для entity IDs и эффект индексов; менять схему только новой forward migration.
- [x] 4. Реализовать: Оптимизировать перенесение в canonical таблицы, порядок FK, access patterns и ограничить temp space.
- [x] 5. Реализовать: Сравнить целостность и результаты до/после, rollback при нарушении FK и overhead добавленных индексов.
- [x] 6. Покрыть автоматическим positive/negative тестом: Корректность FK
- [x] 7. Покрыть автоматическим positive/negative тестом: Контролируемая скорость
- [x] 8. Покрыть автоматическим positive/negative тестом: Независимость collation
- [x] 9. Покрыть автоматическим positive/negative тестом: Возврат к прошлой версии
- [x] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [x] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [x] 12. Обновить тематические docs/, Coverage и ограничения.
- [x] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.

## Реализация и evidence

- Baseline `08d9708`: свежая загрузка 20 001 entities, C/en_US.utf8: полный цикл
  70.378/70.329 с, FK 44.951/44.429 с. Повторные loads заметно быстрее: сравнение
  отдельно для fresh/warm. Regression EXPLAIN test падает на baseline и проходит
  после B04 без machine-specific latency assert.
- После переноса: ANALYZE известных затронутых canonical таблиц в стабильном
  порядке, один SET CONSTRAINTS ALL IMMEDIATE. Никакие FK не отключаются.
- Fact staging переносится/очищается порциями с сохранением одной транзакции;
  stream дополнительно режется до 20k entities, incremental использует slices.
  Temp bytes не являются жёсткой byte-квотой; FK event queue остаётся линейной.
- Новые индексы/collation migration не нужны: C/en_US не показали необходимости
  rewrite PK/FK. Схема и бизнес-семантика имён остаются прежними.
- Million-entity fresh repetitions: 762.416 и 719.186 с полного цикла при бюджете
  900 с, включая committed FK, archive, validation и publication. Во втором
  запуске peak fact staging 7.16 MiB. Использован tmpfs, parser не измеряется.
- При нехватке workspace disk первый незавершённый disk-backed attempt отменён.
  В tmpfs первый полный trial сохранён как log observation; следующий отменён
  до исчерпания квоты. Acceptance repeat выполнен в новой временной БД.
  CLI теперь сохраняет verified completed trials атомарно, incomplete — явно.
- PG15 targeted: 32 passed; затем 4 tests прошли для journal/failure/FK rollback.
  Full PG15 suite после объединения с A03: 1290 passed (324.90s).
  Ruff check и format check прошли. Mandatory PG15 CI: 1290 passed (158.56s),
  success на d703a379801bc9d877b225793f0e9e07fd327e1b.
  https://github.com/resokk/code-crawler/actions/runs/43869595399
  Acceptance подтверждён; change архивирован с сохранением полной спецификации.
- Тематические docs и полный measurement artifact: docs/query-indexes.md,
  docs/ucm-ingestion.md, docs/benchmarks/bulk-pg15-2026-11-16.json.
