# Tasks: Совместное переиспользование проходов SQL и ORM по Java-методам

**Depends on:** B09; желательно B12, B13; existing Java SQL COW и budget.

- [ ] 1. Сверить код на актуальном SHA, записать baseline и profiling evidence для реального bottleneck.
- [ ] 2. Сформулировать контракт и bounds изменения, определить feature flag/fallback.
- [ ] 3. Реализовать изолированное изменение: Добавить per-method tracer числа _recover visits, state clones, SQL/ORM dispatches и CPU; выбрать один подтверждённый hotspot method-heavy fixture.
- [ ] 4. Реализовать изолированное изменение: Выделить immutable shared inputs (method AST boundary, symbol/scope lookup, constant env, resolved API classification) из анализа SQL и JPA без объединения mutable state machines.
- [ ] 5. Реализовать изолированное изменение: Пересчитать downstream SQL construction/execution/ORM только из проверенного intermediate summary; сохранить SQL path budget (default 256) и отдельные parser statuses.
- [ ] 6. Реализовать изолированное изменение: Проверить одинаковые normalized UCM entities, certainty, unresolved candidates, path overflow report и determinism full/incremental.
- [ ] 7. Реализовать изолированное изменение: Включить feature flag для сравнения и быстрого rollback; не делать оптимизацию, если профили не дают выигрыша.
- [ ] 8. Добавить положительный и отрицательный regression scenario: Результат SQL и ORM совпадает
- [ ] 9. Добавить положительный и отрицательный regression scenario: Path budget
- [ ] 10. Добавить положительный и отрицательный regression scenario: Ambiguous dispatch
- [ ] 11. Добавить положительный и отрицательный regression scenario: Incremental parity
- [ ] 12. Запустить differential UCM fact digest + Evidence/Coverage/Certainty parity для baseline и optimized вариантов.
- [ ] 13. Измерить wall/CPU/RSS/disk/WAL на pinned fixture с несколькими trial и оценить накладные расходы/регрессии.
- [ ] 14. При затрагивании БД выполнить PG15 integration/rollback tests, не отключая FK и не редактируя старые миграции.
- [ ] 15. Обновить docs с численными результатами и известными ограничениями.
- [ ] 16. Запустить ruff check, ruff format --check и полный PG15 pytest CI; отметить задачи выполненными только после подтверждения acceptance.
