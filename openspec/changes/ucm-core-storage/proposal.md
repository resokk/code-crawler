# UCM core storage

## Проблема и цель

Repository snapshots пока содержат только metadata. Нужны нормализованные канонические UCM факты с изоляцией snapshots и защитой опубликованного содержимого.

## Границы

Аддитивная migration 0004, PostgreSQL constraints/triggers/indexes и integration tests. Создаём таблицы envelope, source files, symbols, scopes, occurrences, operations, values, relations, evidence, external references и вспомогательные typed tables. Не вводим staging, writer, bulk ingestion, read-side GraphRAG или переключение CLI. Legacy tables сохраняются.
