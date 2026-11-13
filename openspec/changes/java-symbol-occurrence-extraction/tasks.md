# Tasks

- [x] До реализации описать java.symbols contract и ограничения в docs/java-symbols.md.
- [x] Переиспользовать Tree из java.analyze без изменения legacy parse semantics.
- [x] Добавить signatures, constructors, parameters, fields/locals и lexical scopes.
- [x] Добавить declaration/reference/read/write/call occurrences с точными ranges.
- [x] Сохранить unresolved/ambiguous refs и Evidence/Resolution/Certainty/Coverage.
- [x] Исключить неподдерживаемые binding scopes вместо ложного resolution.
- [x] Подключить canonical incremental callback с fail-closed parser diagnostics.
- [x] Добавить 15 unit tests и 1 PostgreSQL incremental/publication test.
- [x] Обновить документацию: PostgreSQL 15 suite — 378 passed; Ruff, format и diff без ошибок.
