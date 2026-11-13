# Tasks

- [x] До реализации описать contract и границы в docs/snapshots.md.
- [x] Добавить аддитивную migration 0003 в public без расширений.
- [x] Добавить explicit repository key и стабильный UUID registration API.
- [x] Добавить snapshot creation и pointer read API.
- [x] Защитить metadata и lifecycle, ограничить pointer ownership через composite FK.
- [x] Проверить upgrade с legacy rows, повторные snapshots и конкурентную регистрацию.
- [x] Проверить весь набор на PostgreSQL 15: 263 passed.
- [x] Выполнить финальные Ruff, format и diff checks: без ошибок.
