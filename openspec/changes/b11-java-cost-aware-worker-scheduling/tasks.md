# Tasks: Адаптивное распределение Java-файлов по процессам

**Depends on:** B09; независимо от B10, но измерить оба сочетания.

- [ ] 1. Сверить код на актуальном SHA, записать baseline и profiling evidence для реального bottleneck.
- [ ] 2. Сформулировать контракт и bounds изменения, определить feature flag/fallback.
- [ ] 3. Реализовать изолированное изменение: Определить дешёвый, безопасный cost estimate для файла (размер, количество methods, SQL candidates/paths по текущему parser catalog) без повторного полного SQL анализа.
- [ ] 4. Реализовать изолированное изменение: Добавить deterministic weighted scheduling при N>1: ограничение задач/bytes in-flight, фиксированный canonical output order независимо от completion order, no prefetch будущих snapshot slices.
- [ ] 5. Реализовать изолированное изменение: Не выбирать автоматически больше CPU, чем разрешает явная настройка, cgroup CPU/memory budget; для малых workloads выполнить в parent sequential path без создания subprocess pool (opt-in adaptive).
- [ ] 6. Реализовать изолированное изменение: Добавить метрики per-worker busy/idle/wall, queue skew, startup overhead и fallback; параметры стратегии не включать в analysis fingerprint, пока normalized facts не меняются.
- [ ] 7. Реализовать изолированное изменение: Сравнить balanced/imbalanced CPU-heavy и catalog-heavy fixtures при workers=1/2/4, с синтетическим тяжёлым и лёгкими файлами.
- [ ] 8. Добавить положительный и отрицательный regression scenario: Нет перекоса по тяжёлому файлу
- [ ] 9. Добавить положительный и отрицательный regression scenario: Последовательный режим остаётся быстрым
- [ ] 10. Добавить положительный и отрицательный regression scenario: Детерминированность фактов
- [ ] 11. Добавить положительный и отрицательный regression scenario: Ресурсная граница
- [ ] 12. Добавить положительный и отрицательный regression scenario: Отмена
- [ ] 13. Запустить differential UCM fact digest + Evidence/Coverage/Certainty parity для baseline и optimized вариантов.
- [ ] 14. Измерить wall/CPU/RSS/disk/WAL на pinned fixture с несколькими trial и оценить накладные расходы/регрессии.
- [ ] 15. При затрагивании БД выполнить PG15 integration/rollback tests, не отключая FK и не редактируя старые миграции.
- [ ] 16. Обновить docs с численными результатами и известными ограничениями.
- [ ] 17. Запустить ruff check, ruff format --check и полный PG15 pytest CI; отметить задачи выполненными только после подтверждения acceptance.
