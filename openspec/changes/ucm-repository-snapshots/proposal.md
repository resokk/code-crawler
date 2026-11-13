# UCM repository snapshots

## Проблема и цель

Legacy repos связывает единственный индекс с basename. Для независимых неизменяемых UCM индексов нужен стабильный repository UUID, история snapshots и отдельный указатель опубликованной версии.

## Границы

Новая миграция в public, metadata API, constraints/triggers и PostgreSQL integration tests. Legacy writer/CLI не переключаются. Факты UCM, staging/COPY, validation gate, атомарная публикация и rollback — следующие changes 09–11.
