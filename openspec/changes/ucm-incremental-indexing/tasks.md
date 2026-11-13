# Tasks

- [x] До реализации описать контракт UCM incremental API и границы CLI в docs/ucm-incremental.md.
- [x] Добавить raw Git output, secure tracked-file capture и fingerprints.
- [x] Добавить FileAnalysis, reverse dependency planning и invalidation profile.
- [x] Добавить migration 0006 для immutable ownership/dependency manifests.
- [x] Переиспользовать загрузку frozen UcmBatch и общий transactional COPY writer.
- [x] Реализовать merged closed batch, повторную source verification и атомарную запись facts/manifests.
- [x] Добавить 15 unit tests и 8 PostgreSQL integration tests.
- [x] Сравнить incremental graph с полным rebuild; проверить failures и immutable metadata.
- [x] Проверить полный набор на PostgreSQL 15: 343 passed; Ruff без ошибок.
- [x] Завершить документацию, проверить format и diff: без ошибок.
