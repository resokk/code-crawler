# Tasks: Снижение повторного построения Java-каталога в subprocess

**Depends on:** B09; использует существующие JavaProcessPool и JavaSourceAdapter.

- [ ] 1. Сверить код на актуальном SHA, записать baseline и profiling evidence для реального bottleneck.
- [ ] 2. Сформулировать контракт и bounds изменения, определить feature flag/fallback.
- [ ] 3. Реализовать изолированное изменение: Добавить измеряемый сериализуемый компактный catalog snapshot из immutable declaration/symbol/signature/owner/URI lookup, исключив AST Node/Tree, DB connection, callbacks и Pydantic facts вне нужного профиля.
- [ ] 4. Реализовать изолированное изменение: Пересылать/подключать каталог к worker один раз при запуске, без повторного полного построения в каждом процессе; безопасно допускать минимальный локальный parse AST для обрабатываемого файла, если он нужен анализатору.
- [ ] 5. Реализовать изолированное изменение: Выбрать transport после замера (memory mapped read-only data или bounded serialized blob/pipe). Зафиксировать версию layout, hashes входных source bytes и fingerprint анализа; malformed/old version отклонять.
- [ ] 6. Реализовать изолированное изменение: Соблюдать owner и lifecycle ресурсов: worker termination/cancel/process crash не оставляет временные файлы, пароли или file descriptors, и не меняет published UCM.
- [ ] 7. Реализовать изолированное изменение: Сравнить startup, total wall/CPU и сумму RSS parent+children для 1/2/4 workers на catalog-heavy и SQL-heavy fixtures.
- [ ] 8. Добавить положительный и отрицательный regression scenario: Одна сериализация каталога
- [ ] 9. Добавить положительный и отрицательный regression scenario: Семантическая эквивалентность
- [ ] 10. Добавить положительный и отрицательный regression scenario: Ошибка worker
- [ ] 11. Добавить положительный и отрицательный regression scenario: Рост ресурсов
- [ ] 12. Запустить differential UCM fact digest + Evidence/Coverage/Certainty parity для baseline и optimized вариантов.
- [ ] 13. Измерить wall/CPU/RSS/disk/WAL на pinned fixture с несколькими trial и оценить накладные расходы/регрессии.
- [ ] 14. При затрагивании БД выполнить PG15 integration/rollback tests, не отключая FK и не редактируя старые миграции.
- [ ] 15. Обновить docs с численными результатами и известными ограничениями.
- [ ] 16. Запустить ruff check, ruff format --check и полный PG15 pytest CI; отметить задачи выполненными только после подтверждения acceptance.
