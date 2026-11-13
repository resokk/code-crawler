# Tasks

- [x] До реализации описать gate, lifecycle, CAS и rollback в docs/ucm-publication.md.
- [x] Добавить migration 0005: receipt, lifecycle gate, unique PUBLISHED и deferred pointer consistency.
- [x] Восстановить модели из всех canonical tables и проверить UcmBatch вне repository lock.
- [x] Добавить freeze/validation/receipt/READY API и повтор validation.
- [x] Добавить короткие CAS publication и rollback API.
- [x] Обновить прежние SQL fixtures для нового validation gate.
- [x] Добавить 17 PostgreSQL tests: gate failures, receipt retry, visibility, concurrency, SQL error и cancellation.
- [x] Проверить полный suite на PostgreSQL 15: 317 passed; Ruff, format и diff без ошибок.
