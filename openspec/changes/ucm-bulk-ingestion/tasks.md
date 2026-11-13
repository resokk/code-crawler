# Tasks

- [x] До реализации описать контракт batch, writer и ограничения в docs/ucm-ingestion.md.
- [x] Добавить замкнутую UcmBatch validation и повторную проверку перед записью.
- [x] Сопоставить все текущие UCM модели с нормализованной схемой.
- [x] Добавить temporary staging/COPY и два прохода canonical INSERT.
- [x] Определить logical→snapshot-scoped physical ID mapping.
- [x] Добавить 9 unit tests для batch и 12 PostgreSQL integration tests.
- [x] Проверить ошибки COPY/canonical write, cancellation, retry и concurrent writers.
- [x] Выполнить весь suite с PostgreSQL 15: 300 passed; Ruff, format и diff checks без ошибок.
