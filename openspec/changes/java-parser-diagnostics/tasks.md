# Tasks

- [x] До реализации описать diagnostics/ranges/provenance в docs/java-diagnostics.md.
- [x] Добавить ParseResult, SourceSpan и typed diagnostics без изменения parse return type.
- [x] Извлечь ERROR/missing nodes, проверить UTF-8 и stable coordinate convention.
- [x] Добавить Symbol.source_span и не создавать declarations с отсутствующими именами.
- [x] Изолировать Parser по вызовам и проверять stat stability при legacy read.
- [x] Сохранить diagnostics в Graph file attrs и вывести через CLI.
- [x] Обновить baseline regression на исправленное поведение.
- [x] Добавить 12 unit tests и 2 PostgreSQL/CLI tests.
- [x] Обновить общую документацию: PostgreSQL 15 suite — 362 passed; Ruff, format и diff без ошибок.
