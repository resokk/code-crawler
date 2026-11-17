# Tasks: Порционная проверка целостности snapshot

**Priority:** P0  
**Dependencies:** B01; разделить на inventory, references и readiness

- [x] 1. Прочитать затрагиваемые исходники и зафиксировать измеримый baseline/падающий тест.
- [x] 2. Реализовать: Сформировать полный реестр UcmBatch semantic invariants с отображением на проверки SQL/stream.
- [x] 3. Реализовать: Проверять unique identities, entity types, typed FK, evidence ranges, relation endpoints, scopes, SQL construction/bindings и ORM инварианты порциями.
- [x] 4. Реализовать: Сохранять validation receipt и READY только по завершении всех проверок в контролируемом транзакционном протоколе.
- [x] 5. Реализовать: Сопоставить решения старого и нового валидатора на корректных и искусственно повреждённых snapshots; убрать обязательную полную model hydration из readiness.
- [x] 6. Покрыть автоматическим positive/negative тестом: Эквивалентность валидации
- [x] 7. Покрыть автоматическим positive/negative тестом: Ограниченное потребление памяти
- [x] 8. Покрыть автоматическим positive/negative тестом: Безопасная публикация
- [x] 9. Покрыть автоматическим positive/negative тестом: Конкурентность
- [x] 10. Добавить миграцию только при новых данных; проверить PG15 FK, rollback, source evidence.
- [x] 11. Сравнить поведение published reader до/после, не поднимать уровень Certainty без Evidence.
- [x] 12. Обновить тематические docs/, Coverage и ограничения.
- [x] 13. Запустить ruff, pytest --require-postgres и benchmark/CI, сохранить воспроизводимые результаты.

## Реализация и evidence

- Реестр: docs/snapshot-validation-invariants.md, включая все families UcmBatch,
  strict per-entity models, ordered/unconsumed rows и SQL counterparts.
- Readiness: fixed-size slices + hard LRU, one-hop batched prefetch; нет all-SQL
  hydration, global Python paths/producers/report sets или parent dictionary.
- SQL EXISTS/GROUP BY для глобальных SQL правил, temporary target/candidate links;
  scope cycles — SQL pointer doubling. Shared local validators сохранены.
- Multiple USES_SQL_CONSTRUCTION descriptors одного execution теперь одинаково
  отклоняются reference и readiness вместо недетерминированного last-wins.
  Существующие canonical facts/receipts не переписываются; отсутствие byte quota
  для отдельной модели и PostgreSQL temporary disk документировано.
- Frozen scan — REPEATABLE READ + shared snapshot lease. Cancellation останавливает
  scheduling reference batches и дожидается worker reads до освобождения connection.
  Receipt/READY — отдельный atomic state check; concurrent READY возвращает stored count,
  concurrent publication не создаёт второй receipt.
- Миграция не нужна: permanent schema не меняется; temporary tables ON COMMIT DROP.
- 29 targeted parity/memory/concurrency tests passed (72.95s). Дополнительно ранее
  23 publication/semantic и 7 lineage/ORM/DB integration tests прошли.
- Memory regression падает на baseline 2951af8: 9320231 bytes > 3006458*1.5;
  проходит на B02. Separate prefetch regression проверяет отсутствие N+1 reads.
- Production-default cache20000/slice2000 SQL-dense measurements, 24002 → 96002
  entities: baseline heap 63.76 → 221.58 MiB; B02 42.95 → 40.38 MiB (factor 0.94).
  Зафиксированные критерии <1.5 growth и <128 MiB выполнены. Без tracer на 96002:
  22.318 s baseline / 12.707 s B02. Protocol/хеши/ограничения — в docs и JSON artifact.
- Full mandatory local PG15 suite: 1354 passed (499.64s), ruff/format passed.
  Main затем дополнен CLI profiler: 17 CLI/profiling/incremental tests passed (7.75s).
  Mandatory PostgreSQL 15 CI на a3739fbb592a1ff40410c3f65e8be615a8cf3053:
  1358 passed (189.72s), success; migrations и working-tree check прошли.
  https://github.com/resokk/code-crawler/actions/runs/44017690441
  Измеренные core module hashes не изменились; acceptance подтверждён.
