# Tasks

- [x] До реализации описать schema contract и ограничения в docs/ucm-storage.md.
- [x] Добавить migration 0004 с envelope/subtype и вспомогательными таблицами.
- [x] Определить snapshot-scoped deferred FKs, discriminator и доменные checks.
- [x] Сохранить SQL registry и сверить с Python registry.
- [x] Добавить guards immutable content и блокировку гонки со state transition.
- [x] Проверить граф, нарушения целостности, snapshot isolation и frozen states на PostgreSQL 15.
- [x] Проверить TRUNCATE CASCADE и конкурентный state transition.
- [x] Выполнить весь suite с PostgreSQL 15: 279 passed (16 новых integration tests).
- [x] Проверить Ruff, format, diff и завершить документацию: без ошибок.
