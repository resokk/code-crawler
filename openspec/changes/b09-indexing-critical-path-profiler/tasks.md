# Tasks: Профилирование критического пути индексации

**Depends on:** Существующий --profile, observability и B01 performance_baseline; независима от B05–B08.

- [ ] 1. Сверить код на актуальном SHA, записать baseline и profiling evidence для реального bottleneck.
- [ ] 2. Сформулировать контракт и bounds изменения, определить feature flag/fallback.
- [ ] 3. Реализовать изолированное изменение: Добавить малозатратные фазовые метрики capture, Java catalog build, parse, calls, SQL recovery, SQLGlot, ORM, DTO enrichment, UCM normalization, spool serialize/deserialize, staging, transfer, deferred FK, readiness и publication. Вложенные интервалы помечать: их нельзя суммировать.
- [ ] 4. Реализовать изолированное изменение: Показывать CPU wall/user/system, Python allocations/peak RSS, bytes/entities/rows, child-process CPU/peak memory, IPC bytes/worker startup; не читать исходный текст и не сохранять SQL или секреты в профиле.
- [ ] 5. Реализовать изолированное изменение: Добавить режим детального профилирования с выключенным по умолчанию трейсингом; baseline без профилирования измерять отдельно из-за накладных расходов.
- [ ] 6. Реализовать изолированное изменение: Сформировать воспроизводимые входы: small, Java SQL path-heavy, catalog-heavy, SQL-dense, 400/1000-file PG15; фиксировать commit SHA и зависимости.
- [ ] 7. Реализовать изолированное изменение: Сохранять machine-readable breakdown/critical path, суммарное время end-to-end и неучтённый остаток; при неполном выполнении явно помечать absent/stopped stage.
- [ ] 8. Добавить положительный и отрицательный regression scenario: Корректные границы этапов
- [ ] 9. Добавить положительный и отрицательный regression scenario: Отсутствие смешивания CPU и ожидания
- [ ] 10. Добавить положительный и отрицательный regression scenario: Параллельная память
- [ ] 11. Добавить положительный и отрицательный regression scenario: Безопасный отчёт
- [ ] 12. Добавить положительный и отрицательный regression scenario: Сбой нагрузки
- [ ] 13. Запустить differential UCM fact digest + Evidence/Coverage/Certainty parity для baseline и optimized вариантов.
- [ ] 14. Измерить wall/CPU/RSS/disk/WAL на pinned fixture с несколькими trial и оценить накладные расходы/регрессии.
- [ ] 15. При затрагивании БД выполнить PG15 integration/rollback tests, не отключая FK и не редактируя старые миграции.
- [ ] 16. Обновить docs с численными результатами и известными ограничениями.
- [ ] 17. Запустить ruff check, ruff format --check и полный PG15 pytest CI; отметить задачи выполненными только после подтверждения acceptance.
