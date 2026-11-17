# Tasks: Безопасный кэш SQLGlot разбора одинаковых запросов

**Depends on:** B09; Java semantic existing; A06 security.

- [ ] 1. Сверить код на актуальном SHA, записать baseline и profiling evidence для реального bottleneck.
- [ ] 2. Сформулировать контракт и bounds изменения, определить feature flag/fallback.
- [ ] 3. Реализовать изолированное изменение: Подсчитать total SQL parse attempts, distinct exact texts, parse errors и CPU SQLGlot отдельно по dialect/version/parse options; не записывать SQL text или его raw hash в общий monitoring.
- [ ] 4. Реализовать изолированное изменение: При подтверждённых дублях реализовать bounded invocation-local LRU для результата разбора или нормализованного immutable summary; ключ учитывает SQL text bytes, dialect, SQLGlot version и parser options.
- [ ] 5. Реализовать изолированное изменение: Не шарить mutable sqlglot.Expression AST между построителями, которые модифицируют узлы; возвращать безопасную копию либо immutable model только при доказанной эквивалентности.
- [ ] 6. Реализовать изолированное изменение: Отдельно кэшировать non-success parse diagnostics без сокрытия SourceRange/варианта/парсинг-статуса; подтверждать partial variants без DataAccess.
- [ ] 7. Реализовать изолированное изменение: Зафиксировать cache hit/miss/size/eviction и сравнить synthetic duplicate-heavy и mostly-unique SQL fixtures.
- [ ] 8. Добавить положительный и отрицательный regression scenario: Кэш только точного запроса
- [ ] 9. Добавить положительный и отрицательный regression scenario: Диалекты изолированы
- [ ] 10. Добавить положительный и отрицательный regression scenario: Mutable AST safety
- [ ] 11. Добавить положительный и отрицательный regression scenario: Неизвестный SQL
- [ ] 12. Добавить положительный и отрицательный regression scenario: Cache bound
- [ ] 13. Запустить differential UCM fact digest + Evidence/Coverage/Certainty parity для baseline и optimized вариантов.
- [ ] 14. Измерить wall/CPU/RSS/disk/WAL на pinned fixture с несколькими trial и оценить накладные расходы/регрессии.
- [ ] 15. При затрагивании БД выполнить PG15 integration/rollback tests, не отключая FK и не редактируя старые миграции.
- [ ] 16. Обновить docs с численными результатами и известными ограничениями.
- [ ] 17. Запустить ruff check, ruff format --check и полный PG15 pytest CI; отметить задачи выполненными только после подтверждения acceptance.
