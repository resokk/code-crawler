# Proposal: Ускорение загрузки через FK и индексы

## Why
При нагрузке ~930 тыс. entities прежний batch не завершился за 50 минут; причины включали FK проверки и текстовые составные ключи.

## Target outcome
Ускорение загрузки через FK и индексы: Измерить COPY staging, INSERT SELECT и SET CONSTRAINTS IMMEDIATE отдельно на PG15. Изучить collations C/locale для entity IDs и эффект индексов; менять схему только новой forward migration. Оптимизировать перенесение в canonical таблицы, порядок FK, access patterns и ограничить temp space. Сравнить целостность и результаты до/после, rollback при нарушении FK и overhead добавленных индексов.

## Scope
- Измерить COPY staging, INSERT SELECT и SET CONSTRAINTS IMMEDIATE отдельно на PG15.
- Изучить collations C/locale для entity IDs и эффект индексов; менять схему только новой forward migration.
- Оптимизировать перенесение в canonical таблицы, порядок FK, access patterns и ограничить temp space.
- Сравнить целостность и результаты до/после, rollback при нарушении FK и overhead добавленных индексов.

## Non-goals
Не отключать FK и не переписывать исторические миграции.

## Dependencies
B01; совместим с B03

## Affected code
src/code_crawler/ingestion.py; src/code_crawler/migrations/; docs/query-indexes.md; tests/integration/test_bulk_ingestion.py

## Priority
P1
