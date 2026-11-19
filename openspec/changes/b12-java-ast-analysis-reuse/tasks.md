# Tasks: Повторное использование Java AST и промежуточного анализа

**Depends on:** B09, совместимо с B10; предшествует B14.

- [ ] 1. Сверить код на актуальном SHA, записать baseline и profiling evidence для реального bottleneck.
- [ ] 2. Сформулировать контракт и bounds изменения, определить feature flag/fallback.
- [ ] 3. Реализовать изолированное изменение: Инструментировать числа Tree-sitter parse calls, symbol extraction и traversal passes отдельно для prepare, Java full analysis, HTTP/Kafka/BPMN enrichment.
- [ ] 4. Реализовать изолированное изменение: Там, где профилем подтверждена повторная работа, передавать immutable per-file parse/symbol scope lookup внутри одного worker/analysis invocation без долгоживущего кеширования Node по repository.
- [ ] 5. Реализовать изолированное изменение: Кэшировать только результаты с зависимостями source_sha256, catalog fingerprint, analyzer profile и версией parser, не включая конфиденциальные сырые исходники в shared cache.
- [ ] 6. Реализовать изолированное изменение: Обеспечить clear-on-file/end-of-slice и после отмены; сохранить exact SourceRange/Evidence/AST diagnostic behavior.
- [ ] 7. Реализовать изолированное изменение: Сравнить parser CPU, file memory и semantic digest до/после на Java + ORM, duplicated FQN и malformed fixtures.
- [ ] 8. Добавить положительный и отрицательный regression scenario: Parser reuse only when equivalent
- [ ] 9. Добавить положительный и отрицательный regression scenario: Инвалидация
- [ ] 10. Добавить положительный и отрицательный regression scenario: Duplicates
- [ ] 11. Добавить положительный и отрицательный regression scenario: Cancellation
- [ ] 12. Запустить differential UCM fact digest + Evidence/Coverage/Certainty parity для baseline и optimized вариантов.
- [ ] 13. Измерить wall/CPU/RSS/disk/WAL на pinned fixture с несколькими trial и оценить накладные расходы/регрессии.
- [ ] 14. При затрагивании БД выполнить PG15 integration/rollback tests, не отключая FK и не редактируя старые миграции.
- [ ] 15. Обновить docs с численными результатами и известными ограничениями.
- [ ] 16. Запустить ruff check, ruff format --check и полный PG15 pytest CI; отметить задачи выполненными только после подтверждения acceptance.
